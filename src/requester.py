import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from utils import format_scryfall_string
import os
import datetime

def get_cardlist(key : str, pauper : bool = False) -> pd.DataFrame:
    filepath = f'data/{"pdhrec" if pauper else "edhrec"}/{key}.csv'
    try:
        mod_date = os.path.getmtime(filepath)
        # if it's been longer than 2 weeks, remove the file and get a new one
        if datetime.datetime.now() - datetime.datetime.fromtimestamp(mod_date) > datetime.timedelta(days=14):
            print(f'Found old file for {key}, removing and getting a new one..')
            os.remove(filepath)
    except:
        pass
    try:
        cardlist_df = pd.read_csv(filepath)
        if len(cardlist_df) == 0:
            print(f'No data for {key}')
            return None
        else:
            return cardlist_df.to_dict('records')
    except:
        print("Could not find a preexisting cardlist, querying...")
        time.sleep(0.5)

    price_reference = pd.DataFrame(columns=['name','price'])
    try:
        price_reference = pd.read_csv('data/scryfall/price_reference.csv', index_col=0)
    except:
        pass
    missing_prices = []
    new_prices = []
    if pauper:
        # Scrape pdhrec for cardlist, and put it into a dict with cols : name, num_decks, potential_decks
        pdhrec_page = requests.get(f'https://www.pdhrec.com/commander/{key}/')
        soup = BeautifulSoup(pdhrec_page.text, 'html5lib')
        potential_decks = 0

        # get the total number of decks, the first one found should be the one we want
        try:
            info = soup.find('div', attrs={"class":"info"})
            # info string: "In X decks"
            potential_decks = int(re.search(r'\d+', info.string).group())
        except:
            print('get_cardlist: pdhrec page is empty')
            # let's make an empty file to indicate that there is no page
            pd.DataFrame(columns=['name','num_decks','potential_decks','synergy']).to_csv(filepath)
            return None

        cardlist = []
        # warning! this search also finds the commander element, should be the first
        hyperlinks = soup.find_all('a', attrs={"class":"gallery-item"})
        # attempting to remove the commander element
        # its an issue with partner commanders, as the structure of that elem is very different
        hyperlinks.pop(0)
        for idx, hyperlink in enumerate(hyperlinks):
            dfc = False
            name = ''
            card = hyperlink.contents[1]
            # double faced cards have a wrapper to show both sides at same time
            if card.name == 'div':
                dfc = True
                card = card.contents[1].contents[3]
            name = card['alt']
            # a bad? encoding of lim-dûl's paladin made this an issue
            name = re.sub('Ã»', 'û', name)
            #pdhrec doesn't handle kongmind's name well, so we have a manual fix
            if 'Kongming,' in name:
                name = 'Kongming, \"Sleeping Dragon\"'

            price = 0.0
            if dfc:
                # pdhrec doesn't have price info for double faced cards, so we gotta grab it from scryfall ourselves
                # lets see if its in the price reference
                price_ref_idx = price_reference.index[price_reference['name']==name].tolist()
                if len(price_ref_idx) > 0:
                    price = price_reference.at[price_ref_idx[0],'price']
                else:
                    missing_prices.append({'name':name,'idx':idx})
            else:
                try:
                    price_str = hyperlink.find('div', attrs={"class":"card-price"}).contents[-1]
                    price = float(re.search(r'\d\.\d\d', price_str).group())
                    new_prices.append({'name':name,'price':price})
                except:
                    # if its not a dfc but pdh doesnt have it, lets see if the reference has it
                    # otherwise we ask scryfall
                    price_ref_idx = price_reference.index[price_reference['name']==name].tolist()
                    if len(price_ref_idx) > 0:
                        price = price_reference.at[price_ref_idx[0],'price']
                    else:
                        print(f"Added {name} to missing prices")
                        missing_prices.append({'name':name,'idx':idx})


            # some pdhrec pages are missing popularities and synergies (see Auspicious Starrix)
            # in this case, we set each value to a default and move on
            num_decks = potential_decks
            synergy = 0
            try:
                num_decks = int(hyperlink['popularity'])
                synergy = float(hyperlink['synergy'])
            except:
                pass

            cardlist.append({'name':name, 'num_decks':num_decks, 'potential_decks':potential_decks, 'synergy':synergy})
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
            pd.DataFrame(columns=['name','num_decks','potential_decks','synergy']).to_csv(filepath)
            return None
        
        # queue cards for prices,and remove unneeded sanitized name fields and edhrec urls
        for idx, card in enumerate(cardlist):
            price_ref_idx = price_reference.index[price_reference['name']==card['name']].tolist()
            if len(price_ref_idx) == 0:
                # try again, but this time mask off any back side card names
                price_ref_idx = price_reference.index[price_reference['name'].str.replace(' // .+', '', regex=True)==card['name']].tolist()
            if len(price_ref_idx) > 0:
                price = price_reference.at[price_ref_idx[0],'price']
                #card['price'] = price
            else:
                missing_prices.append({'name':card['name'],'idx':idx})

            card.pop('sanitized', None)
            card.pop('sanitized_wo', None)
            card.pop('url', None)

    #finally, get the prices for the missing cards
    # we do this in one query to help scryfall out
    if len(missing_prices) > 0:
        query = ""
        missing_prices_df = pd.DataFrame(missing_prices, columns=['name','idx'])
        # first element
        formatted_names = missing_prices_df['name'].apply(format_scryfall_string)
        # scryfall has a limit on accepted URI's so we'll break this into chunks
        block_size = 30
        # could use ceiling here but dont want to import math for some reason
        num_blocks = (len(formatted_names)-1)//block_size + 1

        # first block
        query = f"%28%21%22{formatted_names.iloc[0]}%22"
        if len(formatted_names) > 1:
            query += f"+or+%21%22"
            query += f"%22+or+%21%22".join(formatted_names.iloc[1:block_size])
            query += f"%22"
        query += f"%29"
        cards = scryfall_query([query])

        for b in range(1, num_blocks):
            query = f"%28%21%22{formatted_names.iloc[b*block_size]}%22+or+%21%22"
            query += f"%22+or+%21%22".join(formatted_names.iloc[b*block_size+1:min((b+1)*block_size, len(formatted_names))])
            query += f"%22%29"
            block_cards = scryfall_query([query])
            cards = pd.concat([cards, block_cards],ignore_index=True)

        # this is where the issue is.
        # e.g. missing_prices_df has "Jin Gitaxias"
        # but cards has "Jin Gitaxias // The Great Synthesis"
        names_and_prices = missing_prices_df.merge(cards, on='name',how='outer')
        # if a row x does not have a price, then there is another row y where x.name is in y.name
        # combine the two ...
        #for row in names_and_prices.iterrows():

        no_match = names_and_prices[names_and_prices['price'].isnull()]
        print(no_match.head())
        for row in no_match.itertuples(index=True):
            # for some reason the PDHRec page for Mesmeric Fiend includes Chittering Host, a meld card??
            if row.name not in  ['Forest','Mountain','Plains','Swamp','Island', 'Chittering Host']:
                row_pair_idx = names_and_prices.index[names_and_prices['name'].str.contains(f'{row.name} // ', regex=True)][0]
                names_and_prices.at[row_pair_idx, 'idx'] = int(row.idx)
            names_and_prices.drop(row.Index, inplace=True)
        names_and_prices['idx'] = names_and_prices['idx'].astype('int64')

        # not liking the iterrows usage here....
        for row in names_and_prices.itertuples():
            if not (row.name==cardlist[row.idx]['name'] or cardlist[row.idx]['name'] + ' // ' in row.name):
                print(f'Error: assertion failed on {row.name} and {cardlist[row.idx]["name"]}')
                for i,c in enumerate(cardlist):
                    if c['name'] == row.name:
                        print(f'Actual index was {i}, but used {row.idx}')
                        break
                assert(False)
            #print(f"Adding {row.name} to new prices ({row.price})")
            #cardlist[row.idx]['price'] = row.price
            new_prices.append({'name':row.name, 'price':row.price})


    # finally, add the new prices to the reference for future lookups
    if len(new_prices) > 0:
        pr_size_old = len(price_reference)
        #new_prices = pd.concat([pd.DataFrame(new_prices,columns=['name','price']), cards[['name','price']]], ignore_index=True)
        new_prices = pd.DataFrame(new_prices, columns=['name','price'])
        price_reference = price_reference.merge(new_prices, on='name', how='outer')
        pr_size_new = len(price_reference)
        price_reference['price'] = price_reference['price_y']
        price_reference['price'] = price_reference['price'].combine_first(price_reference['price_x'])
        price_reference.drop(['price_x', 'price_y'], axis=1,inplace=True)
        print(f"added {pr_size_new - pr_size_old} lines to price reference. now {pr_size_new} rows big")
        price_reference.to_csv('data/scryfall/price_reference.csv')
    # save the cardlist so we don't need to query again in the future
    pd.DataFrame(cardlist, columns=['name','num_decks','potential_decks','synergy']).to_csv(filepath)
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
        print(query_str)
    has_next_page = True
    page=1
    cards = pd.DataFrame(columns=['name','color_identity','keywords', 'oracle_text'])
    while has_next_page:
        result_json = requests.get(f'https://api.scryfall.com/cards/search?q={query_str}+cheapest%3Ausd+game%3Apaper&unique=cards&order=edhrec&page={page}&format=json').json()
        if result_json['object']=='error':
            print(f'request error: {result_json["code"]}, {result_json["status"]}')
            print(result_json['details'])
            return None
        has_next_page = result_json['has_more']

        data = pd.DataFrame(result_json['data'])
        # if its all dfc cards, oracle_text will not be in the columns. add a dummy column
        if 'oracle_text' not in data.columns:
            data['oracle_text'] = ''
        card_page = data[['name', 'color_identity', 'keywords', 'oracle_text', 'prices']]

        cards = pd.concat([cards, card_page], ignore_index=True)
        print(f"{min(page*175, result_json['total_cards'])}/{result_json['total_cards']} ({min(1.0, page*175/result_json['total_cards']):.2%})")
        time.sleep(0.5)
        page += 1
    cards['color_identity'] = cards['color_identity'].map(lambda ci: set(ci))
    cards['price'] = cards['prices'].map(lambda prices: prices['eur'] if pd.isna(prices['usd_foil']) else prices['usd_foil'] if pd.isna(prices['usd']) else prices['usd']).astype(float)
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

            oppo_name = commander_partner['name'] + ' ' + commander.name
            if oppo_name in [p['name'] for p in partners]:
                print('oops, this commander pair is already accounted for')
            partners_color_identity = commander.color_identity | commander_partner['color_identity']
            partners.append({'name':partners_name, 'color_identity':partners_color_identity, 'partner':'none'})

    background_query = ['t%3Abackground']
    if pdh:
        background_query.append('r%3Auncommon')

    backgrounds = scryfall_query(background_query)
    
    for commander in choose_background.itertuples():
        for bg in backgrounds.itertuples():
            cbg_name = commander.name + ' ' + bg.name
            cbg_color_identity = commander.color_identity | bg.color_identity
            partners.append({'name':cbg_name, 'color_identity':cbg_color_identity, 'partner':'none'})

    

    for commander in friends_forever.itertuples(index=True):
        for i in range(commander.Index+1, len(friends_forever)):
            commander_partner = friends_forever.iloc[i]
            partners_name = commander.name + ' ' + commander_partner['name']
            partners_color_identity = commander.color_identity |  commander_partner['color_identity']
            partners.append({'name':partners_name, 'color_identity':partners_color_identity, 'partner':'none'})

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
        partners.append({'name':partners_name, 'color_identity':partners_color_identity, 'partner':'none'})

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
    commanders = pd.DataFrame(pd.concat([commanders, generate_partners(commanders)], ignore_index=True))

    # save the file...
    commanders['color_identity'] = commanders['color_identity'].map(lambda ci: repr(ci))
    commanders.to_csv(f'data/scryfall/all_{"pdh_" if pdh else ""}commanders.csv')
    commanders['color_identity'] = commanders['color_identity'].map(lambda ci: eval(ci))

    return commanders