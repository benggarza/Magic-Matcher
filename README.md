# Magic-Matcher
Matches your Magic the Gathering collection with potential commanders using EDHRec

# Scoring

A commander's score is a combination of the number of matched cards and the usage rate of each. For example, if comparing Jodah, Archmage Eternal's EDHRec page to your collection, Leyline of the Guildpact, with a 65% usage rate, is going to hold more weight than Tezzeret's Gambit, with only a 6% usage rate. A score of roughly >= 130 indicates that there are enough quality cards in your collection that you can build a decently working deck. Scores around 180-200 generally indicate a high overlap with a commander precon, which often heavily influences a commander's EDHRec page.

# Usage

Export your Moxfield-formatted collection and place it in the data directory named as "collection.csv". Optionally, export a Moxfield-formatted csv of your commanders and place it in the data directory as "commanders.csv". 

commander_matcher.py is the main workhorse. There are three main functions you will want to use:

- search_all_commanders(num_top, depth, score_threshold, start, color identity): This queries scryfall for a full list of all legal commanders in EDH and compares your collection to the corresponding EDHRec page. All arguments are optional: num_top, the number of commanders you wish to see the final scores of; depth, the number of commanders you wish to search (as of May 20, 2024 there are 2,274 legal commanders); score_threshold, the minimum score to include a commander in the final list; start, the rank number offset to start the list at; and color identity, the color identity of the commanders you wish to search. The start argument is useful if you wish to see a list of commanders you have not already built, or commanders that are not functionally similar to commanders you have built. Commanders you have already built tend to dominate this ranking and are not very insightful.

- search_all_color_identities(num_top): This simply iterates through all 32 different color identities and returns top commander lists of each. Very nice if your collection is one color identity heavy and you want to expand your horizons.

- search_my_commanders(num_top, score_threshold): This function requires that you have a Moxfield-formatted commander csv in the data directory. Instead of searching all legal commanders, this scores only the commanders in your collection (more specifically in your commanders.csv).

To use these functions, edit the main function with your choice of function calls. In the future I will make this script interactive with terminal for easier use.

# Todos

- add terminal interaction support
- GUI integration
- add estimated upgrade costs with each commander score (something like minimum cost to increase score to 150 or something)
- store cardlists after processing to limit api requests
- update card lists after expiration date