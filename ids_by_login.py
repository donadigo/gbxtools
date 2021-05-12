from pygbx import Gbx, GbxType
import sys
import os
import json

def main():
    path = sys.argv[1]
    # login = sys.argv[2]
    i = 0
    reps = {}
    for root, subdirs, files in os.walk(path):
        for filename in files:
            if filename.lower().endswith('.gbx'):
                try:
                    g = Gbx(os.path.join(root, filename))
                    ghost = g.get_classes_by_ids([GbxType.CTN_GHOST, GbxType.CTN_GHOST_OLD])[0]
                    if ghost.login not in reps:
                        reps[ghost.login] = [filename]
                    else:
                        reps[ghost.login].append(filename)

                except:
                    pass
        
        i += 1

    print(json.dumps(reps))

if __name__ == '__main__':
    main()