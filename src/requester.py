import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from utils import format_scryfall_string

def get_cardlist(key : str, pauper : bool = False) -> pd.DataFrame:
    missing_prices = []
    if pauper:
        # Scrape pdhrec for cardlist, and put it into a dict with cols : name, num_decks, potential_decks
        pdhrec_page = requests.get(f'https://www.pdhrec.com/commander/{key}/')
        soup = BeautifulSoup(pdhrec_page.text, 'html.parser')
        potential_decks = 0

        # get the total number of decks, the first one found should be the one we want
        try:
            info = soup.find('div', attrs={"class":"info"})
            # info string: "In X decks"
            potential_decks = int(re.search(r'\d+', info.string).group())
        except:
            print('get_cardlist: pdhrec page is empty')
            return None

        cardlist = []
        # warning! this search also finds the commander element, should be the first
        hyperlinks = soup.find_all('a', attrs={"class":"gallery-item"})
        for idx, hyperlink in enumerate(hyperlinks, start=-1):
            dfc = False
            name = ''
            card = hyperlink.contents[1]
            # double faced cards have a wrapper to show both sides at same time
            if card.name == 'div':
                dfc = True
                card = card.contents[1].contents[3]
            name = card['alt']

            price = 0.0
            if dfc:
                # pdhrec doesn't have price info for double faced cards, so we gotta grab it from scryfall ourselves
                missing_prices.append({'name':name,'idx':idx})
                #card_page = scryfall_card_query(name)
                #if card_page is not None:
                #    price_field = card_page['prices']['usd']
                #    if price_field is None:
                #        price_field = card_page['prices']['usd_foil']
                #    price = float(price_field)
            else:
                price_str = hyperlink.find('div', attrs={"class":"card-price"}).contents[-1]
                price = float(re.search(r'\d\.\d\d', price_str).group())


            # some pdhrec pages are missing popularities and synergies (see Auspicious Starrix)
            # in this case, we set each value to a default and move on
            num_decks = potential_decks
            synergy = 0
            try:
                num_decks = int(hyperlink['popularity'])
                synergy = float(hyperlink['synergy'])
            except:
                pass

            cardlist.append({'name':name, 'num_decks':num_decks, 'potential_decks':potential_decks, 'synergy':synergy, 'price':price})
    else:
        # Grab the json from edhrec
        edhrec_json = requests.get(f'https://json.edhrec.com/pages/commanders/{key}.json').json()

        # if we get a redirect (partner commanders), go there before moving on
        try:
            redirect = edhrec_json['redirect']
            edhrec_json = requests.get(f'https://json.edhrec.com/pages{redirect}.json').json()
        except:
            pass

        cardlist = []
        try:
            cardlist = edhrec_json['cardlist']
        except:
            print('get_cardlist: edhrec json is empty')
            return None
        
        # queue cards for prices,and remove unneeded sanitized name fields and edhrec urls
        for idx, card in enumerate(cardlist):
            missing_prices.append({'name':card['name'],'idx':idx})
            #card_page = scryfall_card_query(card['name'])
            #if card_page is not None:
            #    price_field = card_page['prices']['usd']
            #    if price_field is None:
            #        price_field = card_page['prices']['usd_foil']
            #    price = float(price_field)
            #card['price'] = price

            card.pop('sanitized', None)
            card.pop('sanitized_wo', None)
            card.pop('url', None)

    #finally, get the prices for the missing cards
    # we do this in one query to help scryfall out
    query = ""
    missing_prices_df = pd.DataFrame(missing_prices, columns=['name','idx'])
    # first element
    formatted_names = missing_prices_df['name'].apply(format_scryfall_string)
    # scryfall has a limit on accepted URI's so we'll break this into chunks
    block_size = 30
    num_blocks = len(formatted_names)//block_size + 1

    # first block
    query = f"%28%21%22{formatted_names.iloc[0]}%22+or+%21%22"
    query += f"%22+or+%21%22".join(formatted_names.iloc[1:block_size])
    query += f"%22%29"
    cards = scryfall_query([query])

    for b in range(1, num_blocks):
        query = f"%28%21%22{formatted_names.iloc[b*block_size]}%22+or+%21%22"
        query += f"%22+or+%21%22".join(formatted_names.iloc[b*block_size+1:min((b+1)*block_size, len(formatted_names))])
        query += f"%22%29"
        block_cards = scryfall_query([query])
        cards = pd.concat([cards, block_cards])
    
    #cards_prices = cards[['name','price']]

    names_and_prices = missing_prices_df.merge(cards, on='name')

    # not liking the iterrows usage here....
    for row in names_and_prices.itertuples():
        assert(row.name==cardlist[row.idx]['name'])
        cardlist[row.idx]['price'] = row.price

    return cardlist

def set_partners(commander : pd.Series) -> str:
    partner = 'none'
    # partner with
    if 'Partner with' in commander['keywords']:
        oracle = commander['oracle_text']
        # get beginning and end index of partner name, accounting for potential reminder text
        start = oracle.index('Partner with ') + len('Partner with ')
        end = oracle.index('\n', start)
        reminder_idx = oracle.find('(', start, end)
        if reminder_idx > 0:
            end = reminder_idx - 1
        partner = oracle[start:end]
    elif 'Partner' in commander['keywords']:
        partner = 'Partner'
    elif 'Choose a background' in commander['keywords']:  
        partner = 'Background'
    elif 'Friends forever' in commander['keywords']:
        partner = 'Friends forever'
    elif 'Doctor\'s companion' in commander['keywords']:
        partner = 'Doctor\'s companion'
    return partner

def scryfall_query(queries : list[str]) -> pd.DataFrame:
    query_str = ''
    for q in queries:
        query_str += q + '+'
    has_next_page = True
    page=1
    cards = pd.DataFrame(columns=['name','color_identity','keywords', 'oracle_text'])
    while has_next_page:
        result_json = requests.get(f'https://api.scryfall.com/cards/search?q={query_str}game%3Apaper&unique=cards&order=edhrec&page={page}&format=json').json()
        if result_json['object']=='error':
            print(f'request error: {result_json["code"]}, {result_json["status"]}')
            print(result_json['details'])
            return None
        has_next_page = result_json['has_more']

        data = pd.DataFrame(result_json['data'])
        card_page = data[['name', 'color_identity', 'keywords', 'oracle_text', 'prices']]

        cards = pd.concat([cards, card_page])
        print(f"{min(page*175, result_json['total_cards'])}/{result_json['total_cards']} ({min(1.0, page*175/result_json['total_cards']):.2%})")
        time.sleep(0.5)
        page += 1
    cards['color_identity'] = cards['color_identity'].map(lambda ci: set(ci))
    cards['price'] = cards['prices'].map(lambda prices: prices['usd_foil'] if prices['usd'] is None else prices['usd']).astype(float)
    cards.drop('prices',axis=1,inplace=True)
    return cards

def scryfall_card_query(name : str):
    scryfall_key = re.sub('\W+', '+', name)
    card_page = requests.get(f'https://api.scryfall.com/cards/named?fuzzy={scryfall_key}&format=json').json()
    if card_page['object'] == 'error':
        print(f"Error: scryfall found errors with dfc query: \"{card_page['details']}\" ")
        return None
    return card_page

def generate_partners(commanders : pd.DataFrame, pdh : bool = False) -> pd.DataFrame:
    # pdhrec doesn't do redirects, so the partners must be in alphabetical order
    partner = commanders[commanders['partner']=='Partner'].sort_values(by=['name'])
    # fun fact: Faceless One is both a Background and a Creature with "Choose a Background"
    choose_background = commanders[commanders['partner']=='Background'].sort_values(by=['name'])
    friends_forever = commanders[commanders['partner'] == 'Friends forever'].sort_values(by=['name'])
    partner_withs = commanders[(commanders['partner'] != 'none') &
                               (commanders['partner'] != 'Partner') & (commanders['partner'] != 'Background') &
                               (commanders['partner'] !='Friends forever') & (commanders['partner'] != 'Doctor\'s companion')].sort_values(by=['name'])


    partners = []
    for commander in partner.itertuples(index=True):
        for i in range(commander.Index+1, len(partner)):
            commander_partner = partner.iloc[i]
            partners_name = commander.name + ' ' + commander_partner['name']
            partners_color_identity = commander.color_identity | commander_partner['color_identity']
            partners.append([partners_name, partners_color_identity, 'none'])

    background_query = ['t%3Abackground']
    if pdh:
        background_query.append('r%3Auncommon')

    backgrounds = scryfall_query(background_query)
    
    for commander in choose_background.itertuples():
        for bg in backgrounds.itertuples():
            cbg_name = commander.name + ' ' + bg.name
            cbg_color_identity = commander.color_identity | bg.color_identity
            partners.append([cbg_name, cbg_color_identity, 'none'])

    

    for commander in friends_forever.itertuples(index=True):
        for i in range(commander.Index+1, len(friends_forever)):
            commander_partner = friends_forever.iloc[i]
            partners_name = commander.name + ' ' + commander_partner['name']
            partners_color_identity = commander.color_identity |  commander_partner['color_identity']
            partners.append([partners_name, partners_color_identity, 'none'])

    #doctor_and_companion = []
    #doctor_companion = commanders[commanders['partner'] == 'Doctor\'s companion']
    #for commander in doctor_companion.itertuples(index=True):
    #    for i in range(commander['Index'], len(doctor_companion)):
    #        commander_partner = commanders.iloc[i]
    #        partners_name = commander['name'] + ' ' + commander_partner['name']
    #        partners_color_identity = commander['color_identity'] + commander_partner['color_identity']
    #        doctor_and_companion.append([partners_name, partners_color_identity, 'none'])


    
    for commander in partner_withs.itertuples(index=True):
        partner_name = commander.partner
        commander_partner = partner_withs[partner_withs['name'] == partner_name].iloc[0]
        partners_name = commander.name + ' ' + commander_partner['name']
        partners_color_identity = commander.color_identity | commander_partner['color_identity']

        # try to not have duplicates e.g. Faldan and Pako and Pako and Faldan
        if commander_partner['name'] + ' ' + commander.name in [p[0] for p in partners]:
            continue
        partners.append([partners_name, partners_color_identity, 'none'])

    return pd.DataFrame(partners, columns=commanders.columns)
    


def get_commanders_from_scryfall(pdh : bool = False) -> pd.DataFrame:
    legal_query = 'legal%3Apdh' if pdh else 'legal%3Acommander'

    # uncommon creatures
    commander_query = 't%3Acreature+r%3Auncommon' if pdh else 'is%3Acommander'

    no_bg_query = '-t%3Abackground'

    queries = [legal_query, commander_query, no_bg_query]
    commanders = scryfall_query(queries)

    commanders.loc[:,'partner'] = commanders.apply(set_partners, axis=1)
    commanders.drop(['keywords','oracle_text'], axis=1, inplace=True)

    # the DataFrame cast is just for vscode purposes, not required
    commanders = pd.DataFrame(pd.concat([commanders, generate_partners(commanders)]))

    # save the file...
    commanders['color_identity'] = commanders['color_identity'].map(lambda ci: repr(ci))
    commanders.to_csv(f'data/scryfall/all_{"pdh_" if pdh else ""}commanders.csv')
    commanders['color_identity'] = commanders['color_identity'].map(lambda ci: eval(ci))

    return commanders