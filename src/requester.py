import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from utils import format_keys, format_scryfall_string
import os
from datetime import datetime, timedelta

# TODO : also get scryfall oracle ids for each card as indexing for all dataframes
def get_cardlist(key : str, pauper : bool = False) -> pd.DataFrame:
    filepath = f'data/{"pdhrec" if pauper else "edhrec"}/{key}.csv'
    try:
        mod_date = os.path.getmtime(filepath)
        # if it's been longer than 2 weeks, remove the file and get a new one
        if datetime.now() - datetime.fromtimestamp(mod_date) > timedelta(days=14):
            print(f'Found old file for {key}, removing and getting a new one..')
            os.remove(filepath)
    except:
        pass
    # TODO: handle partner keys being backward
    # i.e. if key = partner1-partner2, check entries for partner1-partner2 and partner2-partner1
    """
    if not pauper:
        try:
            edhrec_entries = pd.read_csv('data/edhrec/edhrecentries.csv',index_col=0)
        except:
            edhrec_entries = requests.get('https://edhrec.com/_next/data/EFt_4NRgLp_vNWVyemdqL/commanders.json').json()
            edhrec_entries = pd.DataFrame(edhrec_entries['pageProps']['data']['cardlist'], columns=['name','sanitized','num_decks'])
            edhrec_entries['key'] = edhrec_entries['sanitized']
            edhrec_entries['key_flipped'] = edhrec_entries['name'] DO SOMETHING
            edhrec_entries.drop(['sanitized','name'],axis=1,inplace=True)
            edhrec_entries.to_csv('data/edhrec/edhrecentries.csv')
        if  len(edhrec_entries[(edhrec_entries['key'] == key]) | (edhrec_entries['key_flipped'] == key])) ==0:
            print(f'edhrec does not have a list for {key}, skipping\n\n')
            return None
        if edhrec_entries[edhrec_entries['key'] == key]['num_decks'].iloc[0] < 10:
            print(f"edhrec does not have enough decks for {key}, skipping")
            return None
    else:
        try:
            pdhrec_entries = pd.read_csv('data/edhrec/pdhrecentries.csv',index_col=0)
        except:
            pdhrec_entries = requests.get('https://www.pdhrec.com/commandernames.json').json()
            pdhrec_entries = pd.Series(pdhrec_entries,name='name').to_frame()
            pdhrec_entries['key'] = format_keys(pdhrec_entries['name'])
            pdhrec_entries.to_csv('data/edhrec/pdhrecentries.csv')
        if len(pdhrec_entries[pdhrec_entries['key'] == key] == 0):
            print(f"pdhrec does not have a page for {key}, skipping")
            return None
    """
    try:
        cardlist_df = pd.read_csv(filepath, index_col=0)
        if len(cardlist_df) == 0:
            return None
        else:
            return cardlist_df
    except:
        print(f"Could not find a preexisting cardlist with key {key}")
        time.sleep(1.0)

    reference = pd.DataFrame(columns=['oracle_id','name','price'])
    try:
        reference = pd.read_csv('data/scryfall/reference.csv', index_col=0)
    except:
        pass
    missing_prices = []
    new_prices = []
    rec_cardlist = []
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
            # Lórien Revealed
            name = re.sub('Ã³', 'ó', name)
            #pdhrec doesn't handle kongmind's name well, so we have a manual fix
            if 'Kongming,' in name:
                name = 'Kongming, \"Sleeping Dragon\"'

            # some pdhrec pages are missing popularities and synergies (see Auspicious Starrix)
            # in this case, we set each value to a default and move on
            num_decks = potential_decks
            synergy = 0
            try:
                num_decks = int(hyperlink['popularity'])
                synergy = float(hyperlink['synergy'])
            except:
                pass

            rec_cardlist.append({'name':name, 'num_decks':num_decks, 'potential_decks':potential_decks, 'synergy':synergy})
    else:
        # Grab the json from edhrec
        edhrec_json = requests.get(f'https://json.edhrec.com/pages/commanders/{key}.json').json()

        # if we get a redirect (partner commanders), go there before moving on
        try:
            redirect = edhrec_json['redirect']
            edhrec_json = requests.get(f'https://json.edhrec.com/pages{redirect}.json').json()
        except:
            pass

        try:
            rec_cardlist = edhrec_json['cardlist']
        except:
            print('get_cardlist: edhrec json is empty')
            pd.DataFrame(columns=['name','num_decks','potential_decks','synergy']).to_csv(filepath)
            return None
    

    # query price reference for each card in cardlist, getting oracle id and price
    cardlist_df = pd.DataFrame(rec_cardlist, columns=['name','num_decks','potential_decks','synergy'])
    card_info = request_cards(cardlist_df)
    assert(len(card_info[card_info['oracle_id'].isna()])==0)

    card_info[['oracle_id','name','num_decks','potential_decks','synergy','price']].to_csv(filepath)
    return card_info

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

# given a dataframe of card names (and other columns...), add the oracle ids, correct names, and prices from either the reference or from scryfall
def request_cards(rec_cardlist : pd.DataFrame):

    ### First, get cards from the reference
    reference = pd.read_csv('data/scryfall/reference.csv',index_col=0)


    # collect info from reference for all cards (use the reference names bc they are more correct)
    card_info = rec_cardlist.merge(reference, how='left', on='name')
    reference['_dfc_name'] = reference['name'].str.extract(r'(^.* \/\/ )')
    card_info['_dfc_name'] = card_info['name'] + ' // '
    #print(reference[reference['_dfc_name'].notna()])
    card_info = card_info.merge(reference, how='left', on='_dfc_name', suffixes=('','_dfc'))
    #print(dfc_info[dfc_info['name'].notna()])
    #card_info['price'] = card_info['price_dfc'].combine_first(card_info['price'])
    #card_info = card_info[['oracle_id','name','_dfc_name','num_decks','potential_decks','synergy','price']]  
    def merge_reference_dfc(row, col):
        if pd.notna(row[f'{col}_dfc']):
            return row[f'{col}_dfc']
        else:
            return row[col]
    for col in ['price', 'oracle_id', 'name','date']:
        card_info[col] = card_info.apply(merge_reference_dfc,args=(col,),axis=1)
    card_info.drop(columns=['oracle_id_dfc', 'name_dfc','price_dfc','date_dfc'],inplace=True)
    #card_info = dfc_info.combine_first(card_info)

    ### Second, query scryfall for cards that either we could not find in reference or whose prices are out of date
    expired_price_mask = datetime.now() - pd.to_datetime(card_info['date'], format='%Y-%m-%d',errors='coerce') > timedelta(days=14)
    missing_info_mask = card_info.isna().any(axis=1)
    # cols: oracle_id, name, color_identity, keywords, oracle_text, price
    cards_missing = card_info['name'][missing_info_mask | expired_price_mask]
    if len(cards_missing) > 0:
        print(f"Querying scryfall for {len(cards_missing)} cards")
        scryfall_card_data = scryfall_cardlist_query( card_info['name'][missing_info_mask | expired_price_mask] )

        # make both the scryfall name and rec name '<frontside name> // '
        scryfall_card_data['_dfc_name'] = scryfall_card_data['name'].str.extract(r'(.* \/\/ )')

        # join card info with missing scryfall data
        card_info = card_info.merge(scryfall_card_data, how='left', on='name', suffixes=('', '_scry'))
        # join card info with missing dfc scryfall data
        card_info = card_info.merge(scryfall_card_data, how='left', on='_dfc_name', suffixes=('','_scry_dfc'))


        # merge the reference, scryfall, and scryfall dfc columns
        def merge_cols(row:pd.Series,col:str):
            if pd.notna(row[f'{col}_scry_dfc']):
                return row[f'{col}_scry_dfc']
            elif f'{col}_scry' in row.index and pd.notna(row[f'{col}_scry']):
                return row[f'{col}_scry']
            else:
                if pd.isna(row[col]):
                    print(f"Warning: all columns for {row['name']}[{col}] are na, most likely an unreleased card.")
                    print(row)
                    #assert(False)
                return row[col]
        for col in ['price', 'oracle_id']:
            card_info[col] = card_info.apply(merge_cols,args=(col,),axis=1)
        card_info.dropna(subset='price', inplace=True)
        card_info['price'] = card_info['price'].astype('float64')
        card_info.drop(card_info.filter(regex='.*_scry.*').columns, axis=1, inplace=True)
    card_info.drop(columns=['_dfc_name','date'],axis=1,inplace=True)
    assert(len(card_info[card_info.isna().any(axis=1)])==0)

    return card_info

def scryfall_cardlist_query(cardnames : pd.Series) -> pd.DataFrame:
    query = ""
    # first element
    #formatted_names = cardnames.apply(format_scryfall_string)
    # scryfall has a limit on accepted URI's so we'll break this into chunks
    block_size = 15
    # could use ceiling here but dont want to import math for some reason
    num_blocks = (len(cardnames)-1)//block_size + 1

    cards = pd.DataFrame(columns=['oracle_id','name','color_identity','keywords', 'oracle_text','price','date'])
    for b in range(0, num_blocks):
        print(f'Block number: {b+1}/{num_blocks}\t{(b+1)/num_blocks:2.1%}')
        query = f"(!%22{cardnames.iloc[b*block_size]}%22"
        if len(cardnames) > b*block_size + 1:
            query += f" or !%22"
            query += f"%22 or !%22".join(cardnames.iloc[b*block_size+1:min((b+1)*block_size, len(cardnames))])
            query += f"%22"
        query += ")"
        #print(query)
        #print(format_scryfall_string(query))
        block_cards = scryfall_query([format_scryfall_string(query)])
        cards = pd.concat([cards, block_cards],ignore_index=True)

    # dropping these, DON'T USE TO GET COMMANDERS
    return cards.drop(columns=['color_identity', 'oracle_text','keywords','date'])

def scryfall_query(queries : list[str]) -> pd.DataFrame:
    query_str = ''
    for q in queries:
        query_str += q + '+'
        #print(query_str)]
    has_next_page = True
    page=1
    cards = pd.DataFrame(columns=['oracle_id','name','color_identity','keywords', 'oracle_text'])
    while has_next_page:
        result = requests.get(f'https://api.scryfall.com/cards/search?q={query_str}+-st%3Amemorabilia+game%3Apaper&order=usd&page={page}&format=json')
        if result.status_code <200 or result.status_code > 399:
            print(f'Received error code {result.status_code}')
        result_json = result.json()
        if result_json['object']=='error':
            print(f'request error: {result_json["code"]}, {result_json["status"]}')
            print(result_json['details'])
            return None
        has_next_page = result_json['has_more']

        data = pd.DataFrame(result_json['data'])
        # if its all dfc cards, oracle_text will not be in the columns. add a dummy column
        if 'oracle_text' not in data.columns:
            data['oracle_text'] = ''
        card_page = data[['oracle_id', 'name', 'color_identity', 'keywords', 'oracle_text', 'prices']]

        # sometimes scryfall gives us a dfc version of a nondfc card like sakashima or jetmir
        weird_cards = card_page[card_page['name'].str.match(r'(.+) \/\/ \1')].copy()
        if len(weird_cards) > 0:
            print("Handling weird cards:")
            print(weird_cards.head())
            print(weird_cards)
            weird_cards['real_name'] = weird_cards['name'].str.extract(r'(.+) \/\/ \1')
            # only <10 cards do this, so manually iterating should be ok for now
            for weird_card in weird_cards.itertuples():
                data_idx = data.index[data['name'] == weird_card.name][0]
                page_idx = card_page.index[card_page['name']==weird_card.name][0]
                oracle_id = data.loc[data_idx,'card_faces'][0]['oracle_id']
                card_page.at[page_idx,'oracle_id'] = oracle_id
                card_page.at[page_idx,'name'] = weird_card.real_name


        cards = pd.concat([cards, card_page], ignore_index=True)
        #print(f"{min(page*175, result_json['total_cards'])}/{result_json['total_cards']} ({min(1.0, page*175/result_json['total_cards']):.2%})")
        time.sleep(0.2)
        page += 1

    
    cards['color_identity'] = cards['color_identity'].map(lambda ci: set(ci))
    cards['oracle_text'] = cards['oracle_text'].fillna('')
    def choose_price(prices):
        if pd.notna(prices['usd']):
            return prices['usd']
        elif 'usd_foil' in prices.keys() and pd.notna(prices['usd_foil']):
            return prices['usd_foil']
        elif 'usd_etched' in prices.keys() and pd.notna(prices['usd_etched']):
            return prices['usd_etched']
        elif 'eur' in prices.keys() and pd.notna(prices['eur']):
            return prices['eur']
        elif 'eur_foil' in prices.keys() and pd.notna(prices['eur_foil']):
            return prices['eur_foil']
        else:
            return pd.NA
    cards['price'] = cards['prices'].map(choose_price)
    #cards['price'] = cards['price'].astype(float)
    cards.drop('prices',axis=1,inplace=True)
    cards['date'] = datetime.now().strftime("%Y-%m-%d")

    # since we had to get card data, let's update the reference while we are at it
    update_reference(cards.dropna(subset='price'))

    return cards

# TODO: pretty sure this function isn't used anymore
def update_reference(new_cards : pd.DataFrame):
    # if a reference doesn't previously exist, we will make a new one
    reference = pd.DataFrame(columns=['oracle_id','name','price','date'])
    try:
        reference = pd.read_csv('data/scryfall/reference.csv',index_col=0)
        reference = reference.merge(new_cards, on='oracle_id', how='outer', suffixes=('_old','_new'))
        reference['price'] = reference['price_new'].combine_first(reference['price_old'])
        reference['date'] = reference['date_new'].combine_first(reference['date_old'])
        reference['name'] = reference['name_old'].combine_first(reference['name_new'])
        reference = reference[['oracle_id','name','price','date']]
    except:
        reference = new_cards[['oracle_id','name','price','date']]
    # we don't want na values sneaking in to the reference list
    if len(reference[reference.isna().any(axis=1)])>0:
        print('error: there are rows being sent to reference with NA values')
        print(reference[reference.isna().any(axis=1)])
    assert(len(reference[reference.isna().any(axis=1)])==0)
    reference.to_csv('data/scryfall/reference.csv')


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
    for commander in partner.itertuples():
        #for i in range(commander.Index+1, len(partner)):
        for commander_partner in partner.itertuples():
            #commander_partner = partner.iloc[i]
            if commander_partner.name == commander.name:
                continue
            partners_name = commander.name + ' & ' + commander_partner.name

            oppo_name = commander_partner.name + ' & ' + commander.name
            if oppo_name in [p['name'] for p in partners]:
                print('oops, this commander pair is already accounted for')
                continue
            partners_color_identity = commander.color_identity | commander_partner.color_identity
            partners.append({'name':partners_name, 'color_identity':partners_color_identity, 'partner':'none'})

    background_query = ['t%3Abackground']
    if pdh:
        background_query.append('r%3Auncommon')

    backgrounds = scryfall_query(background_query)
    
    for commander in choose_background.itertuples():
        for bg in backgrounds.itertuples():
            cbg_name = commander.name + ' & ' + bg.name
            cbg_color_identity = commander.color_identity | bg.color_identity
            partners.append({'name':cbg_name, 'color_identity':cbg_color_identity, 'partner':'none'})

    

    for commander in friends_forever.itertuples():
        #for i in range(commander.Index+1, len(friends_forever)):
        for commander_partner in friends_forever.itertuples():
            if commander.name == commander_partner.name:
                continue
            #commander_partner = friends_forever.iloc[i]
            partners_name = commander.name + ' & ' + commander_partner.name
            oppo_name = commander_partner.name + ' & ' + commander.name
            if oppo_name in [p['name'] for p in partners]:
                continue
            partners_color_identity = commander.color_identity |  commander_partner.color_identity

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
        partners_name = commander.name + ' & ' + commander_partner['name']
        partners_color_identity = commander.color_identity | commander_partner['color_identity']

        # try to not have duplicates e.g. Faldan and Pako and Pako and Faldan
        if commander_partner['name'] + ' & ' + commander.name in [p['name'] for p in partners]:
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
    commanders.drop(['oracle_id','keywords','oracle_text'], axis=1, inplace=True)

    # the DataFrame cast is just for vscode purposes, not required
    commanders = pd.DataFrame(pd.concat([commanders, generate_partners(commanders)], ignore_index=True))

    # save the file...
    commanders['color_identity'] = commanders['color_identity'].map(lambda ci: repr(ci))
    commanders.to_csv(f'data/scryfall/all_{"pdh_" if pdh else ""}commanders.csv')
    commanders['color_identity'] = commanders['color_identity'].map(lambda ci: eval(ci))

    return commanders

def import_collection(filepath : str = 'data/collection/raw_collection.csv'):
    moxfield_collection = pd.read_csv(filepath)
    cardnames = pd.DataFrame(moxfield_collection['Name'].drop_duplicates())
    cardnames['name'] = cardnames['Name']
    card_data = request_cards( cardnames.drop('Name',axis=1) )
    collection = card_data['oracle_id']
    collection.to_csv('data/collection/collection.csv')
    return collection

def import_commanders(filepath : str = 'data/collection/raw_commanders.csv'):
    moxfield_commanders = pd.read_csv(filepath)
    commanders = pd.DataFrame(columns=['name'])
    commanders['name'] = moxfield_commanders['Name']
    commanders.to_csv('data/collection/commanders.csv')

def import_pdh_commanders(filepath : str = 'data/collection/raw_pdh_commanders.csv'):
    moxfield_commanders = pd.read_csv(filepath)
    commanders = pd.DataFrame(columns=['name'])
    commanders['name'] = moxfield_commanders['Name']
    commanders.to_csv('data/collection/pdh_commanders.csv')