""" This script allows to plot the steering inputs over time.
Plotting can be done for multiple replays which will be overlayed. """

import sys
import os

from numpy import int32
import matplotlib.pyplot as plt

from pygbx import Gbx, GbxType
from pygbx.headers import ControlEntry, CGameCtnGhost

def event_to_analog_value(event: ControlEntry):
    """ Converts a ControlEntry event to an analog input. """
    val = int32((event.flags << 16) | event.enabled)
    val <<= int32(8)
    val >>= int32(8)
    return -val

def get_steer_events(events: list[ControlEntry]):
    """ provides a tuple of analog inputs + timestamp from a list of ControlEntry events."""
    steering = []
    time = []

    # Iterate through all events
    for event in events:

        # Only consider steering events
        if event.event_name == 'Steer':
            steering_input = event_to_analog_value(event)

            # Keep original event time handling. Pupose?
            event_time = event.time
            if event_time % 10 == 5:
                event_time -= 65535

            # Add both steering input and timestamp
            steering.append(steering_input)
            time.append(event_time)

    return steering, time

def try_parse_old_ghost(gbx: Gbx):
    """ Carry over from original script 'average_steering_partitions.py.
    Kept to sustain compatibility. """
    ghost = CGameCtnGhost(0)

    parser = gbx.find_raw_chunk_id(0x2401B00F)
    if parser:
        ghost.login = parser.read_string()

    parser = gbx.find_raw_chunk_id(0x2401B011)
    if parser:
        parser.seen_loopback = True
        gbx.read_ghost_events(ghost, parser, 0x2401B011)
        return ghost

    return None

def get_steering_inputs(path: str):
    """ Returns a tuple of steering inputs + timestamp from a given GBX file. """
    try:
        gbx_obj = Gbx(path)
    except Exception as excp:
        print(f'Error parsing: {excp}')
        return None

    ghosts = gbx_obj.get_classes_by_ids([GbxType.CTN_GHOST, GbxType.CTN_GHOST_OLD])

    if not ghosts:
        ghost = try_parse_old_ghost(gbx_obj)
        if not ghost:
            print('Error: no ghosts')
            return None

        if not ghost.control_entries:
            print('Error: no control entries')
            return None
    else:
        ghost = ghosts[0]

    steering_inputs, timeline = get_steer_events(ghost.control_entries)

    return steering_inputs, timeline

def main():
    """ Main Entry Point for 'plot_steering.py'. """

    # Iterate overall multiple replays
    replays = []

    # Check if folder was provided as argument
    path = sys.argv[1]
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for filename in files:
                if filename.lower().endswith('.gbx'):
                    replays.append(os.path.join(root, filename))
    else:
        # No folder was given, consider multiple input files as argumetns
        replays = sys.argv[1::]

    # Iterate over all replays
    for replay in replays:

        # Get steering input per timestamp
        steering_inputs, timeline = get_steering_inputs(replay)

        # Plot the points retrieved
        plt.plot(timeline, steering_inputs)

    # Add X Axis Label
    plt.xlabel('Timeline')
    # Add Y Axis Label
    plt.ylabel('Steering Input')

    # Provide Legend
    replay_names = [os.path.basename(replay_name) for replay_name in replays]
    plt.legend(replay_names)

    # Specify Title
    plt.title('Steering comparison')

    # Finally show the plot
    plt.show()

if __name__ == '__main__':
    main()
