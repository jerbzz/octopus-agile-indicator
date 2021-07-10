"""
Functions to support operation of the Blinkt and Inky displays
"""

from math import ceil
from datetime import datetime, timedelta
import pytz
from tzlocal import get_localzone
from PIL import Image, ImageFont, ImageDraw
from font_roboto import RobotoMedium, RobotoBlack
import yaml
import blinkt
from inky.auto import auto
from inky.eeprom import read_eeprom

# Blinkt! defaults
DEFAULT_BRIGHTNESS = 10

# Inky pHAT defaults
DEFAULT_HIGHPRICE = 15.0
DEFAULT_LOWSLOTDURATION = 3

def update_blinkt(conf: dict, blinkt_data: dict, demo: bool):
    """Recieve a parsed configuration file and price data from the database,
    as well as a flag indicating demo mode, and then update the Blinkt!
    display appropriately."""
    if demo:
        print ("Demo mode. Showing up to first 8 configured colours...")
        print(str(len(conf['Blinkt']['Colours'].items())) + ' colour levels found in config.yaml')
        blinkt.clear()
        i = 0
        for level, data in conf['Blinkt']['Colours'].items():
            print(level, data)
            blinkt.set_pixel(i, data['R'], data['G'], data['B'], conf['Blinkt']['Brightness']/100)
            i += 1

        blinkt.set_clear_on_exit(False)
        blinkt.show()

    else:
        blinkt.clear()
        i = 0
        if len(blinkt_data) < 8:
            print('Not enough data to fill the display - we will get dark pixels.')

        for row in blinkt_data:
            for level, data in conf['Blinkt']['Colours'].items():
                if conf['Mode'] == 'agile_price':
                    slot_data = row[1]
                    if slot_data >= data['Price']:
                        print(str(i) + ': ' + str(slot_data) + 'p -> ' + data['Name'])
                        blinkt.set_pixel(i, data['R'], data['G'], data['B'],
                                         conf['Blinkt']['Brightness']/100)
                        break
                elif conf['Mode'] == 'carbon':
                    slot_data = row[2]
                    if slot_data >= data['Carbon']:
                        print(str(i) + ': ' + str(slot_data) + 'g -> ' + data['Name'])
                        blinkt.set_pixel(i, data['R'], data['G'], data['B'],
                                         conf['Blinkt']['Brightness']/100)
                        break
            i += 1
            if i == 8:
                break

        print ("Setting display...")
        blinkt.set_clear_on_exit(False)
        blinkt.show()

def update_inky(conf: dict, prices: dict, demo: bool):
    """Recieve a parsed configuration file and price data from the database,
    as well as a flag indicating demo mode, and then update the Blinkt!
    display appropriately.

    Notes: list 'prices' as passed from update_display.py is an ordered
    list of tuples. In each tuple, index [0] is the time in SQLite date
    format and index [1] is the price in p/kWh as a float."""
    local_tz = get_localzone()

    try:
        # detect display type automatically
        inky_display = auto(ask_user=False, verbose=True)
    except TypeError as inky_version:
        raise TypeError("You need to update the Inky library to >= v1.1.0") from inky_version

    img = Image.new("P", (inky_display.WIDTH, inky_display.HEIGHT))
    draw = ImageDraw.Draw(img)

    # deal with scaling for newer SSD1608 pHATs
    if inky_display.resolution == (250, 122):
        graph_y_unit = 2.3
        graph_x_unit = 4 # needs to be int to avoid aliasing
        font_scale_factor = 1.2
        x_padding_factor = 1.25
        y_padding_factor = 1.25

    # original Inky pHAT
    if inky_display.resolution == (212, 104):
        graph_y_unit = 2
        graph_x_unit = 3 # needs to be int to avoid aliasing
        font_scale_factor = 1
        x_padding_factor = 1
        y_padding_factor = 1

    if conf['Mode'] == "carbon":
        raise SystemExit("Carbon mode not yet implemented for Inky display.")

    if demo:
        print ("Demo mode... (not implemented!)")

    else:
        # figure out cheapest slots
        low_slot_duration = conf['InkyPHAT']['LowSlotDuration']
        num_low_slots = int(2 * low_slot_duration)
        prices_only = [price[1] for price in prices]
        low_slots_list = []
        for i in range(0, len(prices_only) - num_low_slots - 1):
            low_slots_list.append(sum(prices_only[i:i+num_low_slots])/num_low_slots)
        low_slots_start_idx = low_slots_list.index(min(low_slots_list))
        low_slots_average = "{0:.1f}".format(min(low_slots_list))

        low_slots_start_time = str(datetime.strftime(pytz.utc.localize(
                              datetime.strptime(prices[low_slots_start_idx][0],
                              "%Y-%m-%d %H:%M:%S"),
                              is_dst=None).astimezone(local_tz), "%H:%M"))
        print("Cheapest " + str(low_slot_duration) + " hours: average " +
              low_slots_average + "p/kWh at " + low_slots_start_time + ".")

        min_slot = min(prices, key = lambda prices: prices[1])
        min_slot_price = str(min_slot[1])
        min_slot_time = str(datetime.strftime(pytz.utc.localize(datetime.strptime(min_slot[0],
                              "%Y-%m-%d %H:%M:%S"),
                              is_dst=None).astimezone(local_tz), "%H:%M"))

        print("Lowest priced slot: " + min_slot_price + "p at " + min_slot_time + ".")

        # figure out the cheapest slot

        # draw graph solid bars...
        # shift axis for negative prices
        if min_slot[1] < 0:
            graph_bottom = (inky_display.HEIGHT + min_slot[1]
                            * graph_y_unit) - 13 * y_padding_factor
        else:
            graph_bottom = inky_display.HEIGHT - 13 * y_padding_factor

        i = 0
        for price in prices:
            # draw the lowest slots in black and the highest in red/yellow

            if (i + 1) * graph_x_unit > 127 * x_padding_factor:
                break # don't scribble on the small text

            if low_slots_start_idx <= i < low_slots_start_idx + num_low_slots:
                colour = inky_display.BLACK
            elif price[1] > conf['InkyPHAT']['HighPrice']:
                colour = inky_display.RED
            else:
                colour = inky_display.WHITE

            bar_y_height = price[1] * graph_y_unit

            draw.rectangle(((i + 1) * graph_x_unit, graph_bottom,
                          (((i + 1) * graph_x_unit) - graph_x_unit),
                          (graph_bottom - bar_y_height)), colour)
            i += 1
        # graph solid bars finished

        # draw current price, in colour if it's high...
        # also highlight display with a coloured border if current price is high
        font = ImageFont.truetype(RobotoBlack, size = int(45 * font_scale_factor))
        message = "{0:.1f}".format(prices[0][1]) + "p"
        x_pos = 0 * x_padding_factor
        y_pos = 8 * y_padding_factor

        slot_start = str(datetime.strftime(pytz.utc.localize(datetime.strptime(prices[0][0],
                         "%Y-%m-%d %H:%M:%S"), is_dst=None).astimezone(local_tz), "%H:%M"))

        if prices[0][1] > conf['InkyPHAT']['HighPrice']:
            draw.text((x_pos, y_pos), message, inky_display.RED, font)
            inky_display.set_border(inky_display.RED)
            print("Current price from " + slot_start + ": " + message + " (High)")
        else:
            draw.text((x_pos, y_pos), message, inky_display.BLACK, font)
            inky_display.set_border(inky_display.WHITE)
            print("Current price from " + slot_start + ": " + message)

        # draw time info above current price...
        font = ImageFont.truetype(RobotoMedium, size = int(15 * font_scale_factor))
        message = "Price from " + slot_start + "    " # trailing spaces prevent text clipping
        x_pos = 4 * x_padding_factor
        y_pos = 0 * y_padding_factor
        draw.text((x_pos, y_pos), message, inky_display.BLACK, font)

        mins_until_next_slot = ceil((pytz.utc.localize(datetime.strptime(
                                prices[1][0], "%Y-%m-%d %H:%M:%S"), is_dst=None) - datetime.now(
                                pytz.timezone("UTC"))).total_seconds() / 60)

        print(str(mins_until_next_slot) + " mins until next slot.")

        # draw next 3 slot times...
        font = ImageFont.truetype(RobotoMedium, size = int(15 * font_scale_factor))
        x_pos = 130 * x_padding_factor
        for i in range(3):
            message = "+" + str(mins_until_next_slot + (i * 30)) + ":    "
            # trailing spaces prevent text clipping
            y_pos = i * 18 * y_padding_factor + 3 * y_padding_factor
            draw.text((x_pos, y_pos), message, inky_display.BLACK, font)

        # draw next 3 slot prices...
        x_pos = 163 * x_padding_factor
        for i in range(3):
            message = "{0:.1f}".format(prices[i+1][1]) + "p    "
            # trailing spaces prevent text clipping
            y_pos = i * 18 * y_padding_factor + 3 * y_padding_factor
            if prices[i+1][1] > conf['InkyPHAT']['HighPrice']:
                draw.text((x_pos, y_pos), message, inky_display.RED, font)
            else:
                draw.text((x_pos, y_pos), message, inky_display.BLACK, font)

        # draw separator line...
        ypos = 5 * y_padding_factor + (3 * 18 * y_padding_factor)
        draw.line((130 * x_padding_factor, ypos, inky_display.WIDTH - 5, ypos),
                   fill=inky_display.BLACK, width=2)

        # draw lowest slots info...
        x_pos = 130 * x_padding_factor
        y_pos = 10 * y_padding_factor + (3 * 18 * y_padding_factor)
        font = ImageFont.truetype(RobotoMedium, size = int(13 * font_scale_factor))

        if '.' in str(low_slot_duration):
            lsd_text = str(low_slot_duration).rstrip('0').rstrip('.')
        else:
            lsd_text = str(low_slot_duration)

        draw.text((x_pos, y_pos), lsd_text + "h @" + low_slots_average + "p    ",
                  inky_display.BLACK, font)

        y_pos = 16 * (y_padding_factor * 0.6) + (4 * 18 * y_padding_factor)

        min_slot_timedelta = datetime.strptime(prices[low_slots_start_idx][0],
                              "%Y-%m-%d %H:%M:%S") - datetime.strptime(
                             prices[0][0], "%Y-%m-%d %H:%M:%S")
        draw.text((x_pos, y_pos), low_slots_start_time + "/" +
                  str(min_slot_timedelta.total_seconds() / 3600) +
                   "h    ", inky_display.BLACK, font)

        # draw graph outline (last so it's over the top of everything else)
        i = 0
        for i, price in enumerate(prices):
            colour = inky_display.BLACK
            bar_y_height = price[1] * graph_y_unit
            prev_bar_y_height = prices[i-1][1] * graph_y_unit

            if (i + 1) * graph_x_unit > 127 * x_padding_factor: # don't scribble on the small text
                break

            # horizontal lines...
            draw.line(((i + 1) * graph_x_unit, graph_bottom - bar_y_height,
                     ((i + 1) * graph_x_unit) - graph_x_unit,
                     graph_bottom - bar_y_height), colour)

            # vertical lines...
            if i == 0: # skip the first vertical line
                continue
            draw.line((i * graph_x_unit, graph_bottom - bar_y_height,
                     i * graph_x_unit, graph_bottom - prev_bar_y_height), colour)

            i += 1

        # draw graph x axis
        draw.line((0, graph_bottom, 126 * x_padding_factor, graph_bottom), inky_display.BLACK)

        # draw graph hour marker text...
        for i in range(2, 24, 3):
            colour = inky_display.BLACK
            font = ImageFont.truetype(RobotoMedium, size = int(10 * font_scale_factor))
            x_pos = (i - 0.5) * graph_x_unit * 2 # it's half hour slots!!
            hours = datetime.strftime(datetime.now() + timedelta(hours=i),"%H")
            hours_w, hours_h = font.getsize(hours) # we want to centre the labels
            y_pos = graph_bottom + 1
            if x_pos + hours_w / 2 > 128 * x_padding_factor:
                break # don't draw past the end of the x axis
            draw.text((x_pos - hours_w / 2, y_pos + 1), hours + "  ", inky_display.BLACK, font)
            # and the tick marks for each one
            draw.line((x_pos, y_pos + 2 * y_padding_factor, x_pos, graph_bottom),
                      inky_display.BLACK)

        # draw average line...
        # extract just prices from the list of tuples and put in descending order
        price_list = sorted(list(zip(*prices))[1], reverse=True)
        # now slice off the first (highest) 6 entries
        del price_list[:6]
        # and calculate the mean
        average_price = sum(price_list) / len(price_list)

        average_line_ypos = graph_bottom - average_price * graph_y_unit

        for x_pos in range (0, int(126 * x_padding_factor)):
            if x_pos % 6 == 2: # repeat every 6 pixels starting at 2
                draw.line((x_pos, average_line_ypos, x_pos + 2, average_line_ypos),
                          inky_display.BLACK)

    inky_display.set_image(img)
    inky_display.show()

def clear_display(conf: dict):
    """Determine what type of display is connected and
    use the appropriate method to clear it."""
    if conf['DisplayType'] == 'blinkt':
        print ('Clearing Blinkt! display...')
        blinkt.clear()
        blinkt.show()
        print ('Done.')

    elif conf['DisplayType'] == 'inkyphat':
        inky_eeprom = read_eeprom()
        if inky_eeprom is None:
            raise SystemExit('Error: Inky pHAT display not found')

        print ('Clearing Inky pHAT display...')
        inky_display = auto(ask_user=True, verbose=True)
        colours = (inky_display.RED, inky_display.BLACK, inky_display.WHITE)
        img = Image.new("P", (inky_display.WIDTH, inky_display.HEIGHT))

        for colour in colours:
            inky_display.set_border(colour)
            for x_pos in range(inky_display.WIDTH):
                for y_pos in range(inky_display.HEIGHT):
                    img.putpixel((x_pos, y_pos), colour)
            inky_display.set_image(img)
            inky_display.show()

        print ('Done.')

def deep_get(this_dict: dict, keys: str, default=None):
    """
    Example:
        this_dict = {'meta': {'status': 'OK', 'status_code': 200}}
        deep_get(this_dict, ['meta', 'status_code'])          # => 200
        deep_get(this_dict, ['garbage', 'status_code'])       # => None
        deep_get(this_dict, ['meta', 'garbage'], default='-') # => '-'
    """
    assert isinstance(keys, list)
    if this_dict is None:
        return default
    if not keys:
        return this_dict
    return deep_get(this_dict.get(keys[0]), keys[1:], default)

def get_config() -> dict:
    """
    Read config file and do some basic checks that we have what we need.
    If not, set sensible defaults or bail out.
    """
    try:
        config_file = open('config.yaml', 'r')
    except FileNotFoundError as no_config:
        raise SystemExit('Unable to find config.yaml') from no_config

    try:
        _config = yaml.safe_load(config_file)
    except yaml.YAMLError as config_err:
        raise SystemExit('Error reading configuration: ' + str(config_err)) from config_err

    if _config['DisplayType'] is None:
        raise SystemExit('Error: DisplayType not found in config.yaml')

    if _config['DisplayType'] == 'blinkt':
        print ('Blinkt! display selected.')
        conf_brightness = deep_get(_config, ['Blinkt', 'Brightness'])
        if not (isinstance(conf_brightness, int) and 5 <= conf_brightness <= 100):
            print('Misconfigured brightness value: ' + str(conf_brightness) +
                  '. Using default of ' + str(DEFAULT_BRIGHTNESS) + '.')
            _config['Blinkt']['Brightness'] = DEFAULT_BRIGHTNESS
        if len(_config['Blinkt']['Colours'].items()) < 2:
            raise SystemExit('Error: Less than two colour levels found in config.yaml')

    elif _config['DisplayType'] == 'inkyphat':
        print ('Inky pHAT display selected.')
        inky_eeprom = read_eeprom()
        if inky_eeprom is None:
            raise SystemExit('Error: Inky pHAT display not found')

        conf_highprice = deep_get(_config, ['InkyPHAT', 'HighPrice'])
        if not (isinstance(conf_highprice, (int, float)) and 0 <= conf_highprice <= 35):
            print('Misconfigured high price value: ' + str(conf_highprice) +
                  '. Using default of ' + str(DEFAULT_HIGHPRICE) + '.')
            _config['InkyPHAT']['HighPrice'] = DEFAULT_HIGHPRICE

        conf_lowslotduration = deep_get(_config, ['InkyPHAT', 'LowSlotDuration'])
        if not (conf_lowslotduration % 0.5 == 0 and 0.5 <= conf_lowslotduration <= 6):
            print('Low slot duration misconfigured: ' + str(conf_lowslotduration) +
                  ' (must be between 0.5 and 6 hours in half hour increments).' +
                  ' Using default of ' + str(DEFAULT_LOWSLOTDURATION) + '.')
            _config['InkyPHAT']['LowSlotDuration'] = DEFAULT_LOWSLOTDURATION
    else:
        raise SystemExit('Error: unknown DisplayType ' + _config['DisplayType'] + ' in config.yaml' )

    if _config['Mode'] is None:
        raise SystemExit('Error: Mode not found in config.yaml')

    if _config['Mode'] == 'agile_price':
        print ('Working in Octopus Agile price mode.')
    elif _config['Mode'] == 'carbon':
        print ('Working in carbon intensity mode.')
    else:
        raise SystemExit('Error: Unknown mode found in config.yaml: ' + _config['Mode'])

    if 'DNORegion' not in _config:
        raise SystemExit('Error: DNORegion not found in config.yaml')

    return _config