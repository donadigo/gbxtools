import sys
import os

from typing import List

import numpy as np
from numpy import int32
import matplotlib.pyplot as plt

from pygbx import Gbx, GbxType
from pygbx.headers import ControlEntry, CGameCtnGhost

from scipy import signal
from scipy.interpolate import interp1d

def event_to_analog_value(event: ControlEntry):
    """ Converts a ControlEntry event to an analog input. """
    val = int32((event.flags << 16) | event.enabled)
    val <<= int32(8)
    val >>= int32(8)
    return -val

def get_steer_events(events: List[ControlEntry]):
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

    # Check arguments
    if len(sys.argv) < 2:
        print('No file(s) or path provided.')
        sys.exit()

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
        # No folder was given, consider multiple input files as arguments
        replays = sys.argv[1::]

    if len(replays) != 2:
        raise RuntimeError('Please provide exactly two replays for matching')

    is_first_slowed_down, slowdown_rate = match_replays(replays)
    plot_power_spectral_density(replays[0], 1.)
    plot_power_spectral_density(replays[1], 1.)
    replay_names = [os.path.basename(replay_name)[:25] for replay_name in replays]

    if is_first_slowed_down:
        plot_power_spectral_density(replays[0], slowdown_rate)
        replay_names.append(f'Slowdown x{slowdown_rate:.2f} ' + replay_names[0])
    else:
        plot_power_spectral_density(replays[1], slowdown_rate)
        replay_names.append(f'Slowdown x{slowdown_rate:.2f} ' + replay_names[1])

    plt.legend(replay_names)

    # Specify title
    plt.title('Steering comparison')

    # Finally show the plot
    plt.show()


def match_replays(replays):
    """ Attempts to match two replays by slowing down either one and finding the best fit """
    # Get steering inputs per timestamp
    steer_timeline_a = get_steering_inputs(replays[0])
    steer_timeline_b = get_steering_inputs(replays[1])

    best_loss = 1e30
    best_slowdown = 1.
    is_first_slowed_down = True
    # Scan slowdown rates and compute matching loss, lower is better
    scan_granularity = .05
    for slowdown_factor in np.arange(.3, 1.000001, scan_granularity):
        matching_loss = get_matching_loss(steer_timeline_a, steer_timeline_b, slowdown_factor)
        if matching_loss < best_loss:
            best_loss = matching_loss
            best_slowdown = slowdown_factor
    # Swap a and b to scan slowdown rates for b
    for slowdown_factor in np.arange(.3, 1.000001, scan_granularity):
        matching_loss = get_matching_loss(steer_timeline_b, steer_timeline_a, slowdown_factor)
        if matching_loss < best_loss:
            best_loss = matching_loss
            best_slowdown = slowdown_factor
            is_first_slowed_down = False
    return is_first_slowed_down, best_slowdown


def get_matching_loss(steer_timeline_a, steer_timeline_b, slowdown_factor):
    """ Computes how different two steer/timeline tuples are for a given slowdown factor """
    steering_a, timeline_a = steer_timeline_a
    steering_b, timeline_b = steer_timeline_b
    frequency_a, power_density_a = get_power_spectral_density(timeline_a, steering_a, slowdown_factor)
    frequency_b, power_density_b = get_power_spectral_density(timeline_b, steering_b, 1.)

    # Ignore too low or high frequencies
    low_cutoff = 0.2
    high_cutoff = 30.
    keep_condition_a = (low_cutoff < frequency_a) & (high_cutoff > frequency_a)
    keep_condition_b = (low_cutoff < frequency_b) & (high_cutoff > frequency_b)
    power_density_a = power_density_a[ keep_condition_a ]
    power_density_b = power_density_b[ keep_condition_b ]
    frequency_a = frequency_a[ keep_condition_a ]
    frequency_b = frequency_b[ keep_condition_b ]

    # Resample a such that power densities of a and b are at the same locations
    resample_a = interp1d(frequency_a, power_density_a, fill_value='extrapolate')
    power_density_a_resampled = resample_a(frequency_b)
    # Take log-scale
    log_power_a = np.log(power_density_a_resampled)
    log_power_b = np.log(power_density_b)
    # Compute loss
    loss = ((log_power_a - log_power_b) ** 2).mean()
    return loss


def get_power_spectral_density(timeline, inputs, slowdown_rate=1.):
    """ Returns an array of frequencies and corresponding power densities """
    # Normalize steering to [-1., 1.] interval
    inputs = np.array(inputs) / np.max(np.abs(inputs))

    # Resample steering values to regular interval using last available steering value
    steer_f = interp1d(timeline, inputs, kind='previous', bounds_error=False, fill_value=0)

    # Resample every 10ms
    resampling_rate = 10 * slowdown_rate
    new_x = np.arange(0, timeline[-1], resampling_rate)
    regular_inputs = steer_f(new_x)

    # Compute power spectral density
    sample_frequency = 100.
    frequency, power_density = signal.welch(regular_inputs, sample_frequency, nperseg=512)
    return frequency, power_density


def plot_power_spectral_density(replay, slowdown_rate=1.):
    """ Plots power spectral density for a given replay """
    inputs, timeline = get_steering_inputs(replay)

    frequency, power_density = get_power_spectral_density(timeline, inputs, slowdown_rate)

    plt.semilogy(frequency, power_density)
    plt.xlim([0., 30.])
    plt.xlabel('frequency [Hz]')
    plt.ylabel('PSD [V**2/Hz]')

if __name__ == '__main__':
    main()

