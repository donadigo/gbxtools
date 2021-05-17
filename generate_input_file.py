from pygbx import Gbx, GbxType
from pygbx.headers import ControlEntry, CGameCtnGhost
from numpy import int32
import sys
import os

def strip_all(s: str, tokens: list) -> str:
    for tok in tokens:
        s = s.replace(tok, '')
    
    return s

def get_event_time(event: ControlEntry) -> int:
    if event.event_name == 'Respawn':
        time = int(event.time / 10) * 10
        if event.time % 10 == 0:
            time -= 10
        return time
    else:
        return int(event.time / 10) * 10 - 10

def find_event_end(control_entries: list, target_event: ControlEntry, from_index: int) -> ControlEntry:
    '''
    Even when finding the event ending, we do not discard immediate events such as Steer and Gas.
    If we find that there is an "ending" steer in a negative timestamp, we will discard that later
    in the main loop.
    '''
    # if target_event.event_name in ['Steer', 'Gas']:
    #     return None

    for i in range(from_index, len(control_entries)):
        event = control_entries[i]
        if event.event_name == target_event.event_name: # and (event.enabled == 0 or event.event_name == 'Steer'):
            return event
    
    return None

def should_skip_event(event: ControlEntry):
    if event.event_name in ['AccelerateReal', 'BrakeReal']:
        return event.flags != 1

    if event.event_name == 'Steer':
        return False

    if event.event_name.startswith('_Fake'):
        return True
        
    return event.enabled == 0


def event_to_analog_value(event: ControlEntry):
    val = int32((event.flags << 16) | event.enabled)
    val <<= int32(8)
    val >>= int32(8)
    return -val

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

def try_extract_2020(g: Gbx):
    cbp = g.find_raw_chunk_id(0x0309201D)
    if not cbp:
        return

    print('Pos:', cbp.pos)
    cbp.skip(8) # PIKS + skip size
    cbp.skip(5 * 4) # unknown data
    ticks = cbp.read_uint32()
    print(ticks)

    data_size = cbp.read_uint32()
    print(data_size)
    step = cbp.read_uint32() # something?
    i = 0

    step = ticks / ((data_size - 4) / 2)
    # print(step)
    # cbp.skip(9)
    while i < data_size - 4:
        b = cbp.read_byte()
        print(hex(b), end=' ')
        if b != 0xFF:
            print(hex(b))
            print(i * step)
            i += 2
        else:
            i += 1

def print_inputs(ghost: CGameCtnGhost, write_func=sys.stdout.write):
    is_iface = False
    invert_axis = False
    for event in ghost.control_entries:
        if event.time % 10 == 5 and event.event_name == '_FakeIsRaceRunning':
            is_iface = True

        if event.event_name == '_FakeDontInverseAxis':
            invert_axis = True

    if is_iface:
        for i in range(len(ghost.control_entries)):
            ghost.control_entries[i].time -= 0xFFFF

    for i, event in enumerate(ghost.control_entries):
        if should_skip_event(event):
            continue

        is_unbound = False
        to_event = find_event_end(ghost.control_entries, event, i+1)
        if to_event is not None:
            _to = get_event_time(to_event)
        else:
            _to = ghost.race_time
            if _to == 4294967295:
                _to = -1
                is_unbound = True

        _from = get_event_time(event)

        if _from < 0:
            if _to < 0 and not is_unbound:
                # Does not affect anything in the race
                continue
            else:
                _from = 0

        # Always throw out the millisecond precision
        _from = int(_from / 10) * 10
        _to = int(_to / 10) * 10

        action = 'press'
        key = 'up'

        if event.event_name == 'Accelerate' or event.event_name == 'AccelerateReal':
            key = 'up'
        elif event.event_name == 'SteerLeft':
            key = 'left'
        elif event.event_name == 'SteerRight':
            key = 'right'
        elif event.event_name == 'Brake' or event.event_name == 'BrakeReal':
            key = 'down'
        elif event.event_name == 'Respawn':
            key = 'enter'
        elif event.event_name == 'Steer':
            action = 'steer'
            axis = event_to_analog_value(event)
            if invert_axis:
                axis = -axis
            write_func(f'{_from} {action} {axis}\n')
            continue
        elif event.event_name == 'Gas':
            action = 'gas'
            axis = event_to_analog_value(event)
            if invert_axis:
                axis = -axis

            write_func(f'{_from} {action} {axis}\n')
            continue
        elif event.event_name == 'Horn':
            continue

        if is_unbound:
            write_func(f'{_from} {action} {key}\n')
        else:
            write_func(f'{_from}-{_to} {action} {key}\n')

def process_path(path, write_func):
    g = Gbx(path)

    ghosts = g.get_classes_by_ids([GbxType.CTN_GHOST, GbxType.CTN_GHOST_OLD])
    if not ghosts:
        ghost = try_parse_old_ghost(g)
    else:
        ghost = ghosts[0]

    if not ghost:
        return

    # if not ghost.control_entries:
    #     try_extract_2020(g)
    
    print_inputs(ghost, write_func)

def main():
    if len(sys.argv) < 2:
        print('No provided file!')
        quit()

    path = sys.argv[1]
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for filename in files:
                lower = filename.lower()
                if lower.endswith('.gbx'):
                    out_fname = strip_all(lower, ['.replay.gbx', '.gbx', '\'', '\"', ' ', '$']) + '.txt'
                    with open(out_fname, 'w+') as f:
                        process_path(os.path.join(root, filename), f.write)
    else:
        process_path(path, sys.stdout.write)


if __name__ == '__main__':
    main()
