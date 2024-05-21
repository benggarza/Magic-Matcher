import requests
import pandas
import re
import time
import math
from unidecode import unidecode
from math import sqrt
import sys
from utils import valid_ci, format_keys, get_score, insert, get_index_rank, get_cardlist

def search_my_commanders(num_top : int = 10, score_threshold : float = 0, pdh : bool = False):
    # Grab list of commanders
    commander_df = pandas.read_csv('data/pdh_commanders.csv' if pdh else 'data/commanders.csv')
    commander_names = commander_df['Name'].drop_duplicates()
    commander_keys = format_keys(commander_names)

    collection_df = pandas.read_csv('data/collection.csv')
    collection_names = collection_df['Name'].drop_duplicates().to_list()

    search_commanders(commander_keys, commander_names, collection_names, 'my', num_top=num_top, score_threshold=score_threshold, pdh=pdh)

def search_all_commanders(num_top : int = 10, depth : int = sys.maxsize, score_threshold : float = 0, start : int = 0, ci : str = None, pdh : bool = False):
    if ci is not None and not valid_ci(ci):
            print(f"Error: Invalid color identity {ci}")
            exit(1)

    collection_df = pandas.read_csv('data/collection.csv')
    collection_names = collection_df['Name'].drop_duplicates().to_list()

    ci_query = ''
    if ci is not None:
        ci_query = f'ci%3D{ci}'

    legal_query = 'legal%3Apdh' if pdh else 'legal%3Acommander'

    # uncommon creatures
    commander_query = 't%3Acreature+r%3Auncommon' if pdh else 'is%3Acommander'

    no_bg_query = '-t%3Abackground'

    commander_names = pandas.Series()
    try:
        commander_df = pandas.read_csv(f'data/{ci if ci is not None else "all"}_{"pdh_" if pdh else ""}commanders.csv')
        commander_names = commander_df['name']
    except:
        print("Downloading commander list from scryfall...")
        has_next_page = True
        page=1
        while has_next_page:
            commander_json = requests.get(f'https://api.scryfall.com/cards/search?q={legal_query}+{commander_query}+{ci_query}+{no_bg_query}+game%3Apaper&unique=cards&order=edhrec&page={page}&format=json').json()
            has_next_page = commander_json['has_more']
            commander_names = pandas.concat([commander_names, pandas.Series([card['name'] for card in commander_json['data']])])
            print(f"{min(page*175, commander_json['total_cards'])}/{commander_json['total_cards']} ({min(1.0, page*175/commander_json['total_cards']):.2%})")
            time.sleep(0.5)
            page += 1
        pandas.DataFrame(commander_names, columns=['name']).to_csv(f'data/{ci if ci is not None else "all"}_{"pdh_" if pdh else ""}commanders.csv')

    commander_names = commander_names.iloc[start:min(start+depth, len(commander_names))]

    commander_keys = format_keys(commander_names)

    search_commanders(commander_keys, commander_names, collection_names, ci if ci is not None else 'all', num_top=num_top, score_threshold=score_threshold, pdh=pdh)

def search_commanders(commander_keys : pandas.Series, commander_names : pandas.Series, collection : list, category_name : str,
                      num_top : int = 10, score_threshold : float = 0,
                      pdh : bool = False):
    best_commanders = [""]*num_top
    best_scores = [0]*num_top
    best_nums = [0]*num_top
    # For each commander...
    for i, (commander_name, commander_key) in enumerate(zip(commander_names, commander_keys)):
        print(f"{i+1}/{len(commander_names)}: Evaluating {commander_name}")
        cardlist = get_cardlist(commander_key, pauper=pdh) 
        if cardlist is None:
            print(f'Error: {commander_name} ({commander_key}) did not return cardlist. Skipping..')
            continue

        namelist = [card['name'] for card in cardlist]
        scorelist = [get_score(card['num_decks'],card['potential_decks'], pdh=pdh) for card in cardlist]
        #print(namelist)

        # Count how many cards from collection show up in recommended cards (maybe have a bag-of-cards list for indices)
        commander_score = 0
        num_cards = 0
        for name, score in zip(namelist, scorelist):
            if name in collection:
                commander_score += score
                num_cards += 1
        print(f"Score: {commander_score:3.3f}\tNum Cards: {num_cards:3d}")
        if commander_score > score_threshold:
            commander_rank = get_index_rank(commander_score, best_scores)
            if commander_rank > -1:
                insert(commander_score, commander_rank, best_scores)
                insert(commander_name, commander_rank, best_commanders)
                insert(num_cards, commander_rank, best_nums)
        #print(best_commander_scores, top_5_commanders)
        time.sleep(0.5)

    # trim any empty elements from the lists
    i = num_top
    for i in range(num_top-1, 0, -1):
        if best_scores[i-1] != 0:
            break
    best_commanders = best_commanders[:i]
    best_scores = best_scores[:i]
    best_nums = best_nums[:i]

    print()
    # Show the commanders with the top counts
    with open(f'reports/commanderlists/top_{category_name}_{"pdh_" if pdh else ""}commanders.txt','w') as f:
        for rank, (cname, cscore, cnum) in enumerate(zip(best_commanders, best_scores, best_nums)):
            print(f"Rank {rank+1:2d}:\t{cname:31}\tnum cards {cnum:3d}\t score {cscore:3.3f}")
            f.write(f"Rank {rank+1:2d}:\t{cname:31}\tnum cards {cnum:3d}\t score {cscore:3.3f}\n")

def get_commander_cardlist(commander_name : str, pdh : bool = False):
    commander_df = pandas.read_csv(f'data/all_{"pdh_" if pdh else ""}commanders.csv')
    if commander_name not in commander_df['name'].to_list():
        print(f"Error: {commander_name} is an invalid commander name")
        exit(1)

    commander_key = format_keys(pandas.Series([commander_name]))[0]

    collection_df = pandas.read_csv('data/collection.csv')
    collection_names = collection_df['Name'].drop_duplicates().to_list()

    rec_cardlist = get_cardlist(commander_key, pauper=pdh)
    namelist = [card['name'] for card in rec_cardlist]
    percentlist = [card['num_decks']/card['potential_decks'] for card in rec_cardlist]
    scorelist = [get_score(card['num_decks'], card['potential_decks']) for card in rec_cardlist]

    cardlist = []
    sum_score = 0
    print(f"\n{commander_name}\n")
    for name, percent, score in zip(namelist, percentlist, scorelist):
        if name in collection_names:
            print(f"{name:31}\t{percent:.0%}")
            cardlist.append((name, percent))
            sum_score += score

    with open(f'reports/cardlists/{commander_name}_{"pdh_" if pdh else ""}cardlist.txt', 'w') as f:
        f.write(f"{commander_name:31}\tscore: {sum_score:3.3f}\tnum cards: {len(cardlist):3d}\n\n")
        for card in cardlist:
            f.write(f"{card[0]:31}\t{card[1]:3.0%}\n")

    return cardlist

# Looks at the cards NOT in my collection
# calculates the score/price ratio for each card and sorts in descending order
def get_scoreprice_list(commander_name :str):
    cardlist = get_commander_cardlist(commander_name)

    return None

def search_all_color_identities(num_top : int = sys.maxsize, pdh : bool = False):
    #search_my_commanders(20)
    # test color identity filtering
    colors = ['w','u','b','r','g']
    color_pairs = ['rakdos','golgari','selesnya','boros','dimir','azorius','orzhov', 'izzet', 'simic','gruul']
    color_trios = ['jund', 'naya', 'bant', 'mardu', 'esper', 'jeskai', 'grixis', 'sultai', 'abzan', 'temur']
    # colorless commanders
    search_all_commanders(20, 2000, 0,ci='c', pdh=pdh)

    # monocolor
    for monocolor in colors:
        search_all_commanders(20, 2000, 0,ci=monocolor, pdh=pdh)
    # pair colors
    for color_pair in color_pairs:
        search_all_commanders(20, 2000, 0, ci=color_pair, pdh=pdh)
    # trios
    for color_trio in color_trios:
        search_all_commanders(20, 2000, 0, ci=color_trio, pdh=pdh)
    # 4 color
    for i in range(len(colors)):
        four_color = ''
        for j in range(i+1, len(colors)):
            four_color += colors[j]
        for j in range(0, i):
            four_color += colors[j]
        search_all_commanders(10, 2000, 0, ci=four_color, pdh=pdh)

    # search five color
    search_all_commanders(20, 2000, 0, ci='wubrg', pdh=pdh)

def main():
    # start with a general top list
    #search_all_commanders(num_top=100, pdh=True)
    # then search through each color identity
    #search_all_color_identities()
    # THEN search through my commanders
    search_my_commanders(30, pdh=True)

if __name__ == '__main__':
    main()
