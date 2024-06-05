import requests
import pandas as pd
import re
import time
import math
from unidecode import unidecode
from math import sqrt
import sys
from os import path, mkdir
from utils import valid_ci, format_keys, get_score, insert, get_index_rank, get_ci_set
from requester import get_cardlist, get_commanders_from_scryfall, import_collection, import_commanders, import_pdh_commanders

def search_my_commanders(num_top : int = 10, score_threshold : float = 0, pdh : bool = False,
                         ci : str = None, sort_by : str = False):
    # Grab list of commanders
    commander_df = pd.read_csv('data/collection/pdh_commanders.csv' if pdh else 'data/collection/commanders.csv')
    #if ci:
    #    commander_df = commander_df[commander_df['color_identity'] == get_ci_set(ci)]
    commander_names = commander_df.drop_duplicates()['name']
    commander_keys = format_keys(commander_names)

    collection = pd.read_csv('data/collection/collection.csv',index_col=0)

    search_commanders(commander_keys, commander_names, collection, 'my', num_top=num_top, score_threshold=score_threshold, pdh=pdh, sort_by=sort_by)

def search_all_commanders(num_top : int = 10, depth : int = sys.maxsize,
                          score_threshold : float = 0, start : int = 0,
                          ci : str = None, pdh : bool = False, sort_by : str = 'score'):
    if ci is not None and not valid_ci(ci):
            print(f"Error: Invalid color identity {ci}")
            exit(1)

    collection_df = pd.read_csv('data/collection/collection.csv',index_col=0).drop_duplicates()
    #collection_names = collection_df['Name'].drop_duplicates().to_list()

    commanders = pd.DataFrame()
    try:
        commanders = pd.read_csv(f'data/scryfall/all_{"pdh_" if pdh else ""}commanders.csv', converters={'color_identity': eval})
    except:
        print("Downloading commander list from scryfall...")
        commanders = get_commanders_from_scryfall(pdh=pdh)

    commanders_color = commanders
    if ci is not None:
        ci_set = get_ci_set(ci)
        commanders_color = commanders[commanders['color_identity'] == ci_set]

    commander_names = commanders_color['name']

    commander_names = commander_names.iloc[start:min(start+depth, len(commander_names))]

    commander_keys = format_keys(commander_names)

    search_commanders(commander_keys, commander_names, collection_df,
                      ci, num_top=num_top,
                      score_threshold=score_threshold, pdh=pdh, sort_by=sort_by)

# TODO: remove as many of these iterations as possible, replace with merges, vector operations
def search_commanders(commander_keys : pd.Series, commander_names : pd.Series, collection : pd.DataFrame, category_name : str,
                      num_top : int = 10, score_threshold : float = 0,
                      pdh : bool = False, sort_by : str = 'score'):
    
    commander_results = []

    skiplist = []
    try:
        skiplist = pd.read_csv('data/collection/skip.csv')['name'].to_list()
    except:
        pass
    # For each commander...
    for i, (commander_name, commander_key) in enumerate(zip(commander_names, commander_keys)):
        # skip commanders in skiplist
        if commander_name in skiplist:
            print(f"{commander_name} found in skiplist, skipping...")
            continue
        print(f"{i+1}/{len(commander_names)}: Evaluating {commander_name}")
        cardlist = get_cardlist(commander_key, pauper=pdh) 
        if cardlist is None:
            print(f'Error: {commander_name} ({commander_key}) did not return cardlist. Skipping..')
            continue
        elif len(cardlist) < 60:
            print(f'{commander_name}: not enough cards to analyze, skipping')
            continue
        elif (not pdh and cardlist['potential_decks'].mean() < 100) or (pdh and cardlist['potential_decks'].mean() < 4):
            print(f'{commander_name}: not enough decks to analyze, skipping')
            continue

        cardlist['score'] = cardlist.apply(get_score, axis=1, pdh=pdh)

        in_collection = cardlist.merge(collection, on='oracle_id', how='inner')

        # find all the cards not in the collection
        _nic = cardlist.merge(collection, on='oracle_id', how='left', indicator=True)
        if len(_nic)==0:
            print("NO MISSING CARDS")
        not_in_collection = _nic[_nic['_merge']=='left_only']

        commander_score = in_collection['score'].sum()
        missing_score = not_in_collection['score'].sum()
        num_cards = len(in_collection)

        cost_difference = not_in_collection['price'].dot(not_in_collection['num_decks'].div(not_in_collection['potential_decks']))

        e_cost_to_180 = (cost_difference/missing_score)*max(180-commander_score, 0)

        # an estimation of how much bang for your buck is in the cards you would need to buy
        score_cost = cost_difference/missing_score
        score_rel = commander_score/cardlist['score'].sum()


        print(f"Score: {commander_score:3.3f}\tNum Cards: {num_cards:3d}\tCost Diff: {cost_difference:3.3f}\tMissing score : {missing_score:3.3f}\tScore Cost: {score_cost}")
        commander_results.append({'name':commander_name, 'score':commander_score,'num_cards':num_cards,
                                  'cost_diff': cost_difference, 'missing_score':missing_score, 
                                  'score_cost':score_cost,'score_rel':score_rel,'cost_to_180':e_cost_to_180})

    commander_results_df = pd.DataFrame(commander_results, columns=['name','score','num_cards','cost_diff', 'missing_score','score_cost', 'score_rel','cost_to_180'])
    if sort_by=='cost_diff':
        commander_results_df.sort_values(by=['cost_diff'], axis=0, ascending=True, ignore_index=True, inplace=True)
    elif sort_by=='score_cost': # score_not_in_collection/cost_diff
        commander_results_df.sort_values(by=['score_cost'], axis=0, ascending=True, ignore_index=True, inplace=True)
    elif sort_by=='missing_score':
        commander_results_df.sort_values(by=['missing_score'], axis=0, ascending=True, ignore_index=True, inplace=True)
    elif sort_by=='score_rel':
        commander_results_df.sort_values(by=['score_rel'], axis=0, ascending=False, ignore_index=True, inplace=True)
    elif sort_by=='cost_to_180':
        commander_results_df.sort_values(by=['cost_to_180'], axis=0, ascending=True, ignore_index=True, inplace=True)
    else: # sorting by score
        commander_results_df.sort_values(by=['score'], axis=0, ascending=False, ignore_index=True, inplace=True)

    print()
    # Show the commanders with the top counts
    format_dir = ""
    try:
        if pdh:
            format_dir = "pdh/"
            mkdir('reports/commanderlists/pdh')
        else:
            format_dir = "edh/"
            mkdir('reports/commanderlists/edh')
    except:
        pass
    report_path = f'reports/commanderlists/{format_dir}'
    report_name = f'top{f"_{category_name}_" if category_name else ""}{"_pdh_" if pdh else ""}commanders_by_{sort_by}.txt'
    with open(report_path+report_name,'w') as f:
        print(category_name)
        print(f"Rank:\tCommander Name\t\t\t\t\t\t\t\tNum Cards\tScore\tMissing\tCost Diff\tScore Cost\tCost to 180")
        f.write(f"Rank:\tCommander Name \t\t\t\t\t\t\t\t\t\t\t\t\t\tNum Cards\tScore\tMissing\tCost Diff\tScore Cost\tCost to 180\n")
        for row in commander_results_df.itertuples(index=True):
            rank = row.Index
            if rank > num_top:
                break
            cname = row.name
            cscore = row.score
            cmscore = row.missing_score
            cnum = row.num_cards
            ccost = row.cost_diff
            cscore_cost = row.score_cost
            cto180 = row.cost_to_180
            print(f"{rank+1:2d}:\t{cname:70}\t{cnum:3d}\t\t{cscore:3.1f}\t{cmscore:3.1f}\t${ccost:4.2f}\t\t${cscore_cost:3.2f}\t${cto180:3.2f}")
            f.write(f"{rank+1:2d}:\t{cname:70}\t{cnum:3d}\t\t\t{cscore:3.1f}\t{cmscore:3.1f}\t${ccost:4.2f}\t${cscore_cost:3.2f}\t${cto180:3.2f}\n")

def get_commander_cardlist(commander_name : str, pdh : bool = False):
    commander_df = pd.read_csv(f'data/scryfall/all_{"pdh_" if pdh else ""}commanders.csv')
    if commander_name not in commander_df['name'].to_list():
        print(f"Error: {commander_name} is an invalid commander name")
        exit(1)

    commander_key = format_keys(pd.Series([commander_name]))[0]

    collection = pd.read_csv('data/collection/collection.csv',index_col=0)

    rec_cardlist = get_cardlist(commander_key, pauper=pdh)
    rec_cardlist['score'] = rec_cardlist.apply(get_score, axis=1, pdh=pdh)

    in_collection = rec_cardlist.merge(collection, on='oracle_id', how='inner')
    commander_score = in_collection['score'].sum()
    num_cards = len(in_collection)

    with open(f'reports/cardlists/{commander_name}_{"pdh_" if pdh else ""}cardlist.txt', 'w') as f:
        f.write(f"{commander_name:80}\tscore: {commander_score:3.3f}\tnum cards: {num_cards:3d}\n\n")
        for card in in_collection.itertuples():
            f.write(f"{card.name:80}\t{card.score:3.1f}\n")

    return in_collection

def search_all_color_identities(num_top : int = sys.maxsize, pdh : bool = False, sort_by: str ='cost_diff'):
    # test color identity filtering
    colors = ['w','u','b','r','g']
    color_pairs = ['rakdos','golgari','selesnya','boros','dimir','azorius','orzhov', 'izzet', 'simic','gruul']
    color_trios = ['jund', 'naya', 'bant', 'mardu', 'esper', 'jeskai', 'grixis', 'sultai', 'abzan', 'temur']
    # colorless commanders
    search_all_commanders(20, 2000, 0,ci='c', pdh=pdh, sort_by=sort_by)

    # monocolor
    for monocolor in colors:
        search_all_commanders(20, 2000, 0,ci=monocolor, pdh=pdh, sort_by=sort_by)
    # pair colors
    for color_pair in color_pairs:
        search_all_commanders(20, 2000, 0, ci=color_pair, pdh=pdh, sort_by=sort_by)
    # trios
    for color_trio in color_trios:
        search_all_commanders(20, 2000, 0, ci=color_trio, pdh=pdh, sort_by=sort_by)
    # 4 color
    for i in range(len(colors)):
        four_color = ''
        for j in range(i+1, len(colors)):
            four_color += colors[j]
        for j in range(0, i):
            four_color += colors[j]
        search_all_commanders(10, 2000, 0, ci=four_color, pdh=pdh, sort_by=sort_by)

    # search five color
    search_all_commanders(20, 2000, 0, ci='wubrg', pdh=pdh, sort_by=sort_by)

def init():
    if not path.exists('data/collection/collection.csv'):
        import_collection()
    if not path.exists('data/collection/commanders.csv'):
        import_commanders()
    if not path.exists('data/collection/pdh_commanders.csv'):
        import_pdh_commanders()

def main():
    # start with a general top list
    search_all_commanders(num_top=100,pdh=False,sort_by='cost_to_180')
    search_all_commanders(num_top=50,pdh=True,sort_by='cost_to_180')
    # then search through each color identity
    #search_all_color_identities(num_top=50,pdh=False, sort_by='cost_to_180')
    #search_all_commanders(num_top=40,ci='b', sort_by='cost_diff')
    search_all_color_identities(num_top=50, pdh=True, sort_by='cost_to_180')
    # THEN search through my commanders
    ##search_my_commanders(30)
    #search_my_commanders(30, pdh=True)
    #get_commander_cardlist('Vilis, Broker of Blood')

if __name__ == '__main__':
    init()
    main()
