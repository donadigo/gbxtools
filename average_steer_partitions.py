import json
from pygbx import Gbx, GbxType
from pygbx.headers import ControlEntry, CGameCtnGhost
from numpy import int32
import sys
import os
from pprint import pprint

SPIKE_THRESHOLD = 10
TIME_PERIOD = 1000
NOISE_THRESHOLD = 2000
TARGET_VERSION_PREFIX = 'TmForever.'

if len(sys.argv) < 2:
    print('No file or path provided.')
    quit()

def event_to_analog_value(event: ControlEntry):
    val = int32((event.flags << 16) | event.enabled)
    val <<= 8
    val >>= 8
    return -val

def partition_steer_events(events: list, sample_period: int):
    p = []
    current = []
    boundary = sample_period
    for ev in events:
        if ev.event_name == 'Steer':
            current.append(event_to_analog_value(ev))

        etime = ev.time
        if etime % 10 == 5:
            etime -= 65535
        
        if sample_period != -1 and etime > boundary:
            if current:
                p.append(current)
            current = []
            boundary += sample_period

    return p

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

def analyze_replay(path: str):
    try:
        g = Gbx(path)
    except Exception as e:
        print(f'Error parsing: {e}')
        return None

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

    ghost = ghosts[0]
    results = {'version': ghost.game_version, 'login': ghost.login, 'max_spikes': 0, 'spikes': 0}

    partitions = partition_steer_events(ghost.control_entries, TIME_PERIOD)
    spikes = []
    for partition in partitions:
        spikes_num = -1

        spike_dir = 0
        for i in range(1, len(partition)):
            diff = partition[i] - partition[i - 1]
            if abs(diff) <= NOISE_THRESHOLD:
                continue

            if diff > 0 and spike_dir != 1:
                spike_dir = 1
                spikes_num += 1
            elif diff < 0 and spike_dir != -1:
                spike_dir = -1
                spikes_num += 1
            

        spikes_num = max(0, spikes_num)
        spikes.append(spikes_num)

    if len(spikes) == 0:
        max_spikes = 0
    else:
        max_spikes = max(spikes)

    results['max_spikes'] = max_spikes
    results['spikes'] = spikes

    return results

def main():
    failed = 0
    processed = 0
    spike_data = {}

    path = sys.argv[1]
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for filename in files:
                if filename.lower().endswith('.gbx'):
                    try:
                        results = analyze_replay(os.path.join(root, filename))
                        if results:
                            # if not results['version'].startswith(TARGET_VERSION_PREFIX):
                            #     continue

                            processed += 1
                            login = results['login']
                            replay_max_spikes_num = results['max_spikes']
                            replay_spikes = results['spikes']

                            if replay_max_spikes_num >= SPIKE_THRESHOLD:
                                avg_spikes = round(sum(replay_spikes)/len(replay_spikes), 2)
                                print(f'{login}, {filename},{replay_max_spikes_num},{avg_spikes}')
                            
                            if login in spike_data:
                                spike_data[login]['max_spikes'].append(replay_max_spikes_num)
                                spike_data[login]['spikes'].extend(replay_spikes)
                            else:
                                spike_data[login] = {'max_spikes': [replay_max_spikes_num], 'spikes': replay_spikes}
                        else:
                            failed += 1
                    except Exception as e:
                        failed += 1

        print(f'Processed successfully: {processed}, failed to analyze: {failed}')
        with open('spike_data.json', 'w+') as f:
            data = json.dumps(spike_data)
            f.write(data)
    else:
        results = analyze_replay(path)
        if results:
            # pprint(results)
            login = results['login']
            replay_max_spikes_num = results['max_spikes']
            spikes_len = len(results['spikes'])
            if spikes_len > 0:
                avg_spikes = round(sum(results['spikes'])/len(results['spikes']), 2)
            else:
                avg_spikes = 0

            print(f'{login},{replay_max_spikes_num},{avg_spikes}')

if __name__ == '__main__':
    main()