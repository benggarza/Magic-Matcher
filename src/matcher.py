from commander_matcher import search_all_color_identities, search_all_commanders, search_my_commanders, get_commander_cardlist

def main():
    while(True):
        command = input("commander matcher $ ")
        argv = command.split(' ')
        print(argv)
        argc = len(argv)
        cmd = argv[0]
        # search usage: search ci|all [-my] [-pdh] [-top n] [-sort score|cost_to_180]
        if cmd=='search':
            if True:#try:
                # pauper arg
                pdh = '-pdh' in argv

                # color identity arg
                all = 'all' == argv[1]
                ci = argv[1].lower()

                # my commanders
                my = '-my' in argv

                # num top arg
                if '-top' in argv:
                    top_i = argv.index('-top')
                else:
                    top_i = -1
                n_top = 10
                if top_i>0:
                    n_top = int(argv[top_i+1])

                # sorting arg
                sort_by = 'score'
                if '-sort' in argv:
                    sort_i = argv.index('-sort')
                else:
                    sort_i = -1
                if sort_i>0:
                    sort_by = argv[sort_i+1]

                if my:
                    search_my_commanders(num_top=n_top, ci=None if all else ci, pdh=pdh, sort_by=sort_by)
                else:
                    search_all_commanders(num_top=n_top, ci=None if all else ci, pdh=pdh, sort_by=sort_by)
            #except:
            #    print("usage error: search ci|all [-my] [-pdh] [-top n] [-sort score|cost_to_180]")
        # fullsearch usage: fullsearch [-pdh] [-top n] [-sort score|cost_to_180]
        elif cmd=='fullsearch':
            if True:#try:
                # pauper arg
                pdh = '-pdh' in argv

                # num top arg
                if '-top' in argv:
                    top_i = argv.index('-top')
                else:
                    top_i = -1
                n_top = 10
                if top_i>0:
                    n_top = int(argv[top_i+1])

                # sorting arg
                sort_by = 'score'
                if '-sort' in argv:
                    sort_i = argv.index('-sort')
                else:
                    sort_i = -1
                if sort_i>0:
                    sort_by = argv[sort_i+1]

                search_all_color_identities(num_top=n_top, pdh=pdh, sort_by=sort_by)
            #except:
            #    print("usage error: fullsearch [-pdh] [-top n] [-sort score|cost_to_180]")
        # get usage: get commander_name [-pdh]
        elif cmd=='get':
            if True:#try:
                pdh = argv[-1] == '-pdh'
                if pdh:
                    commander_name = ' '.join(argv[1:-1])
                else:
                    commander_name = ' '.join(argv[1:])

                get_commander_cardlist(commander_name=commander_name, pdh=pdh)
            #except:
            #    print("usage error: get commander_name [-pdh]")
        elif cmd=='exit':
            break
        else:
            print("Usage error")


if __name__=="__main__":
    main()