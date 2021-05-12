import json
from pygbx import Gbx, GbxType
from pygbx.headers import ControlEntry, CGameCtnGhost
import sys
import os
from pprint import pprint

TIME_PERIOD = 1000

if len(sys.argv) < 2:
    print('No file or path provided.')
    quit()

def try_parse_old_ghost(g: Gbx):
    ghost = CGameCtnGhost(0)

    parser = g.find_raw_chunk_id(0x2401B00F)
    if parser:
        ghost.login = parser.read_string()

    parser = g.find_raw_chunk_id(0x2401B011)
    if parser:
        parser.seen_loopback = True
        g.read_ghost_events(ghost, parser, 0x2401B011)
        return ghost

    return None

def partition_binary_events(events: list, sample_period: int):
    p = []
    current = []
    boundary = sample_period
    for ev in events:
        if (ev.event_name == 'SteerLeft' or ev.event_name == 'SteerRight') and ev.enabled == 1:
            current.append(1)

        etime = ev.time
        if etime % 10 == 5:
            etime -= 65535
        
        if sample_period != -1 and etime > boundary:
            if current:
                p.append(current)
            current = []
            boundary += sample_period

    return p

def uses_binary_input(path: str):
    try:
        g = Gbx(path)
    except:
        print(f'Error parsing: {e}')

    ghosts = g.get_classes_by_ids([GbxType.CTN_GHOST, GbxType.CTN_GHOST_OLD])
    if not ghosts:
        ghost = try_parse_old_ghost(g)
        if not ghost:
            print('Error: no ghosts')
            return None

        if not ghost.control_entries:
            print('Error: no control entries')
            return None
    else:
        ghost = ghosts[0]

    results = {'version': ghost.game_version, 'login': ghost.login, 'max_taps': 0, 'taps': 0}

    ghost = ghosts[0]
    if ghost.login != 'acceleracer_01':
        return None

    for entry in ghost.control_entries:
        if entry.event_name == 'Steer':
            return None

    partitions = partition_binary_events(ghost.control_entries, TIME_PERIOD)
    # print(partitions)

    m = 0
    for p in partitions:
        m = max(m, len(p))

    results['max_taps'] = m
    results['taps'] = partitions
    return results

def main():
    path = sys.argv[1]
    if os.path.isdir(path):
        directory = os.fsencode(path)

        for file in os.listdir(directory):
            filename = os.fsdecode(file)
            if filename.lower().endswith('.gbx'):
                try:
                    results = uses_binary_input(os.path.join(path, filename))
                    if results:
                        login = results['login']
                        max_taps = results['max_taps']
                        print(f'{login} {filename},{max_taps}')
                except Exception as e:
                    pass
    else:
        results = uses_binary_input(path)
        print(results)

if __name__ == '__main__':
    main()