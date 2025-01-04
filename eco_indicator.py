"""
Functions to support operation of the Blinkt and Inky displays
"""

import yaml

# Blinkt! defaults
DEFAULT_BRIGHTNESS = 10
DEFAULT_SLOTSPERPIXEL = 1

# Inky pHAT defaults
DEFAULT_HIGHPRICE = 30.0
DEFAULT_LOWSLOTDURATION = 3
DEFAULT_DATADURATION = 24

def update_blinkt(conf: dict, blinkt_data: dict, demo: bool):
    """Recieve a parsed configuration file and price data from the database,
    as well as a flag indicating demo mode, and then update the Blinkt!
    display appropriately."""

    import blinkt

    if demo:
        print("Demo mode. Showing up to first 8 configured colours...")
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

        if conf['Mode'] == "carbon":
            tuple_idx = 2
            short_unit = "g"
            data_name = "Carbon"

        if conf['Mode'] == "agile_import":
            tuple_idx = 1
            short_unit = "p"
            data_name = "Price"

        if conf['Mode'] == "agile_export":
            tuple_idx = 1
            short_unit = "p"
            data_name = "Export"

        if conf['Mode'] == "tracker":
            tuple_idx = 1
            short_unit = "p"
            data_name = "Tracker"
            raise SystemExit("Tracker not yet implemented on Blinkt!")

        slots_per_pixel = conf['Blinkt']['SlotsPerPixel']

        print("Displaying " + str(slots_per_pixel) + " slots per Blinkt! pixel.")

        # group data into however many slots we are using per pixel
        blinkt_data = [blinkt_data[i:i + slots_per_pixel] for i in range(0, len(blinkt_data), slots_per_pixel)]

        # calculate the mean for the grouped data and replace the group with one list item
        new_data = []

        for group in blinkt_data:

            total_sum = sum(item[tuple_idx] for item in group)
            mean = round(total_sum / len(group),1)

            first_item = list(group[0])
            first_item[tuple_idx] = mean

            new_data.append([tuple(first_item)])

        blinkt_data = new_data

        if len(blinkt_data) < 8:
            print("Not enough data to fill the display - we will get dark pixels.")

        blinkt.clear()
        i = 0
        for row in blinkt_data:
            for level, data in conf['Blinkt']['Colours'].items():
                slot_data = row[0][tuple_idx]
                if slot_data >= data[data_name]:
                    print(str(i) + ': ' + str(slot_data) + short_unit + ' -> ' + data['Name'])
                    blinkt.set_pixel(i, data['R'], data['G'], data['B'],
                                     conf['Blinkt']['Brightness']/100)
                    break
            i += 1
            if i == 8:
                break

        print("Setting display...")
        blinkt.set_clear_on_exit(False)
        blinkt.show()

def update_inky_tracker(conf: dict, inky_data: dict, demo: bool):
    """Recieve a parsed configuration file and price/carbon data from the database,
    as well as a flag indicating demo mode, and then update the Inky
    display appropriately.

    Notes: list 'inky_data' as passed from update_display.py is an ordered
    list of tuples. In each tuple, index [0] is the time in SQLite date
    format, index [1] is the electricity price in p/kWh as a float, index [2]
    is blank as it would be the carbon intensity, and index [3] is the gas price."""

    from datetime import datetime
    from datetime import timedelta
    from PIL import Image, ImageFont, ImageDraw
    from font_roboto import RobotoMedium, RobotoBlack
    from inky.auto import auto
    from inky.eeprom import read_eeprom

    def price_diff_to_symbol(price_today: float, price_tomorrow: float) -> tuple[str, int]:

        diff = price_tomorrow - price_today
        change = diff / price_today

        if change == 0:
            return "( - )", inky_display.BLACK
        elif 0 < change < 0.1:
            return "( ^ )", inky_display.BLACK
        elif change >= 0.1:
            return "( ^^ )", inky_display.RED
        elif 0 > change > -0.1:
            return "( v )", inky_display.BLACK
        elif change <= -0.1:
            return "( vv )", inky_display.RED
        else:
            return "bork", inky_display.RED

    if demo:
        raise SystemExit("Demo mode not implemented!")

    inky_eeprom = read_eeprom()

    if inky_eeprom is None:
        raise SystemExit("Error: Inky pHAT display not found")

    try:
        # detect display type automatically
        inky_display = auto(ask_user=False, verbose=True)
    except TypeError as inky_version:
        raise TypeError("You need to update the Inky library to >= v1.1.0") from inky_version

    img = Image.new("P", (inky_display.WIDTH, inky_display.HEIGHT), inky_display.WHITE)
    draw = ImageDraw.Draw(img)

    # deal with scaling for newer SSD1608 pHATs
    if inky_display.resolution == (250, 122):
        font_scale_factor = 1.2
        x_scale_factor = 1.25
        y_scale_factor = 1.25

    # original Inky pHAT
    if inky_display.resolution == (212, 104):
        font_scale_factor = 1
        x_scale_factor = 1
        y_scale_factor = 1

    # Inky Impression 7.3
    if inky_display.resolution == (800, 480):
        font_scale_factor = 2
        x_scale_factor = 3
        y_scale_factor = 2
        graph_x_width = 126 * x_scale_factor    

    today = datetime.now().date()
    print("Today is " + today.strftime("%a %-d %b %Y"))

    tracker_latest_date = datetime.strptime(inky_data[0][0], "%Y-%m-%d %H:%M:%S") + timedelta(hours = 12)
    tracker_latest_date = tracker_latest_date.date()
    datedif = tracker_latest_date - today

    check = 0 # 0 = nothing for tomorrow.
              # 1 = elec, but no gas
              # 2 = gas, but no elec
              # 3 = both gas and elec for tomorrow

    if datedif.days > 1 or datedif.days < 0:
        raise SystemExit("Error: impossible date difference of " + str(datedif) + " days!")

    elif datedif.days == 0: # no database entry for today so no data yet at all
        print("We don't have any data for tomorrow yet.")
        elec_tracker_price_today = inky_data[0][1]
        gas_tracker_price_today = inky_data[0][3]
        check = 0

    elif datedif.days == 1: # there is either gas, electricity, or both.
        elec_tracker_price_tomorrow = inky_data[0][1]
        elec_tracker_price_today = inky_data[1][1]
        gas_tracker_price_tomorrow = inky_data[0][3]
        gas_tracker_price_today = inky_data[1][3]

        if isinstance(elec_tracker_price_tomorrow, float):
            check = check + 1

        if isinstance(gas_tracker_price_tomorrow, float):
            check = check + 2

        if check == 0:
            raise SystemExit("Error: we seem to have a database entry for tomorrow"
                              "but there doesn't seem to be valid data in it.")
    else:
        raise SystemExit("Epic Fail. If we got here, mathematics itself is broken.")

    # draw info and today's date

    font = ImageFont.truetype(RobotoMedium, size=int(20 * font_scale_factor))
    x_pos = 4 * x_scale_factor
    y_pos = 0 * y_scale_factor
    draw.text((x_pos, y_pos), "Gas", inky_display.BLACK, font)
    x_pos = (inky_display.WIDTH) - (40 * x_scale_factor)
    draw.text((x_pos, y_pos), "Elec", inky_display.BLACK, font)

    font = ImageFont.truetype(RobotoBlack, size=int(15 * font_scale_factor))
    date_string = today.strftime("%a %-d %b")
    width, height = draw.textsize(date_string, font)
    x_pos = (inky_display.WIDTH / 2) - (width / 2)
    draw.text((x_pos, y_pos), date_string, inky_display.BLACK, font)

    # draw separator line

    x_pos = inky_display.WIDTH / 2
    draw.line((x_pos, 20 * y_scale_factor, x_pos, inky_display.HEIGHT - 5),
          fill=inky_display.BLACK, width=2)

    # draw today's prices

    font = ImageFont.truetype(RobotoBlack, size=int(35 * font_scale_factor))
    x_pos = 4 * x_scale_factor
    y_pos = 20 * y_scale_factor
    draw.text((x_pos, y_pos), "{:.1f}p".format(gas_tracker_price_today), inky_display.RED, font)
    x_pos = inky_display.WIDTH - (95 * x_scale_factor)
    draw.text((x_pos, y_pos), "{:.1f}p".format(elec_tracker_price_today), inky_display.RED, font)
    print("Electricity Tracker price today: {:.2f}p".format(elec_tracker_price_today))
    print("Gas Tracker price today: {:.2f}p".format(gas_tracker_price_today))

    # draw "Tomorrow" labels

    font = ImageFont.truetype(RobotoMedium, size=int(15 * font_scale_factor))
    x_pos = 4 * x_scale_factor
    y_pos = 60 * y_scale_factor
    draw.text((x_pos, y_pos), "Tomorrow:", inky_display.BLACK, font)
    x_pos = inky_display.WIDTH - (95 * x_scale_factor)
    draw.text((x_pos, y_pos), "Tomorrow:", inky_display.BLACK, font)

    # draw tomorrow's data or draw a placeholder

    if check == 1 or check == 3: # we have electricity data for tomorrow
        font = ImageFont.truetype(RobotoMedium, size=int(20 * font_scale_factor))
        x_pos = inky_display.WIDTH - (95 * x_scale_factor)
        y_pos = 75 * y_scale_factor
        draw.text((x_pos, y_pos), "{:.1f}p".format(elec_tracker_price_tomorrow), inky_display.BLACK, font)
        symbol, colour = price_diff_to_symbol(elec_tracker_price_today, elec_tracker_price_tomorrow)
        font = ImageFont.truetype(RobotoMedium, size=int(15 * font_scale_factor))
        draw.text((x_pos + 60 * x_scale_factor, y_pos + 3 * y_scale_factor), symbol, colour, font)
        print("Electricity Tracker price tomorrow: {:.2f}p".format(elec_tracker_price_tomorrow))

    if check == 2 or check == 3: # we have gas data for tomorrow
        font = ImageFont.truetype(RobotoMedium, size=int(20 * font_scale_factor))
        x_pos = 4 * x_scale_factor
        y_pos = 75 * y_scale_factor
        draw.text((x_pos, y_pos), "{:.1f}p".format(gas_tracker_price_tomorrow), inky_display.BLACK, font)
        symbol, colour = price_diff_to_symbol(gas_tracker_price_today, gas_tracker_price_tomorrow)
        font = ImageFont.truetype(RobotoMedium, size=int(15 * font_scale_factor))
        draw.text((x_pos + 60 * x_scale_factor, y_pos + 3 * y_scale_factor), symbol, colour, font)
        print("Gas Tracker price tomorrow: {:.2f}p".format(gas_tracker_price_tomorrow))

    font = ImageFont.truetype(RobotoMedium, size=int(15 * font_scale_factor))

    if check == 0 or check == 1: # we don't have gas data for tomorrow
        x_pos = 4 * x_scale_factor
        y_pos = 75 * y_scale_factor
        draw.text((x_pos, y_pos), "No data yet.", inky_display.BLACK, font)
        print("No gas data for tomorrow yet.")

    if check == 0 or check == 2: # we don't have electricity data for tomorrow
        x_pos = inky_display.WIDTH - (95 * x_scale_factor)
        y_pos = 75 * y_scale_factor
        draw.text((x_pos, y_pos), "No data yet.", inky_display.BLACK, font)
        print("No electricity data for tomorrow yet.")

    if conf['InkyPHAT']['DisplayOrientation'] == 'inverted':
        img=img.rotate(180)

    inky_display.set_image(img)
    inky_display.show()

def update_inky(conf: dict, inky_data: dict, demo: bool):
    """Recieve a parsed configuration file and price/carbon data from the database,
    as well as a flag indicating demo mode, and then update the Inky
    display appropriately.

    Notes: list 'inky_data' as passed from update_display.py is an ordered
    list of tuples. In each tuple, index [0] is the time in SQLite date
    format and index [1] is the price in p/kWh as a float. index [2] is
    the carbon intensity as an integer."""

    if demo:
        raise SystemExit("Demo mode not implemented!")

    from math import ceil
    from datetime import datetime, timedelta
    import pytz
    from tzlocal import get_localzone
    from PIL import Image, ImageFont, ImageDraw
    from font_roboto import RobotoMedium, RobotoBlack
    from inky.auto import auto
    from inky.eeprom import read_eeprom

    inky_eeprom = read_eeprom()

    if inky_eeprom is None:
        raise SystemExit("Error: Inky pHAT display not found")

    local_tz = get_localzone()

    try:
        # detect display type automatically
        inky_display = auto(ask_user=False, verbose=True)
    except TypeError as inky_version:
        raise TypeError("You need to update the Inky library to >= v1.1.0") from inky_version
    #make an image framebuffer, explicit background colour of white (required for some Inky displays)
    img = Image.new("P", (inky_display.WIDTH, inky_display.HEIGHT), inky_display.WHITE)
    draw = ImageDraw.Draw(img)

    # deal with scaling for newer SSD1608 pHATs
    if inky_display.resolution == (250, 122):
        font_scale_factor = 1.2
        x_scale_factor = 1.25
        y_scale_factor = 1.25
        graph_x_width = 126 * x_scale_factor

    # original Inky pHAT
    if inky_display.resolution == (212, 104):
        font_scale_factor = 1
        x_scale_factor = 1
        y_scale_factor = 1
        graph_x_width = 126 * x_scale_factor

    # Inky Impression 7.3
    if inky_display.resolution == (800, 480):
        font_scale_factor = 2
        x_scale_factor = 3
        y_scale_factor = 2
        graph_x_width = 126 * x_scale_factor    

    data_duration = conf['InkyPHAT']['DataDuration']
    graph_x_unit = graph_x_width / (data_duration * 2) # half hour slots!

    if conf['Mode'] == "carbon":
        tuple_idx = 2
        short_unit = "g"
        descriptor = "Carbon at "
        high_value = conf['InkyPHAT']['HighIntensity']
        format_str = "{:.0f}"

    if conf['Mode'] == "agile_import":
        tuple_idx = 1
        short_unit = "p"
        descriptor = "Price from "
        high_value = conf['InkyPHAT']['HighPrice']
        format_str = "{0:.1f}"


    if conf['Mode'] == "agile_export":
        tuple_idx = 1
        short_unit = "p"
        descriptor = "Export at "
        high_value = conf['InkyPHAT']['HighPrice']
        format_str = "{0:.1f}"

    # figure out highest priced slots
    high_slot_duration = conf['InkyPHAT']['LowSlotDuration']
    num_high_slots = int(2 * high_slot_duration)
    inky_data_only = [slot_data[tuple_idx] for slot_data in inky_data]
    high_slots_list = []
    for i in range(0, len(inky_data_only) - num_high_slots - 1):
        high_slots_list.append(sum(inky_data_only[i:i+num_high_slots])/num_high_slots)
    high_slots_start_idx = high_slots_list.index(max(high_slots_list))
    high_slots_average = format_str.format(max(high_slots_list))

    high_slots_start_time = str(datetime.strftime(pytz.utc.localize(
        datetime.strptime(inky_data[high_slots_start_idx][0], "%Y-%m-%d %H:%M:%S"),
        is_dst=None).astimezone(local_tz), "%H:%M"))

    print("Highest " + str(high_slot_duration) + " hours: average " +
          high_slots_average + short_unit + "/kWh at " + high_slots_start_time + ".")

    max_slot = max(inky_data, key=lambda inky_data: inky_data[tuple_idx])
    max_slot_value = str(max_slot[tuple_idx])
    max_slot_time = str(datetime.strftime(pytz.utc.localize(datetime.strptime(
        max_slot[0], "%Y-%m-%d %H:%M:%S"), is_dst=None).astimezone(local_tz), "%H:%M"))

    print("Highest value slot: " + max_slot_value + short_unit + " at " + max_slot_time + ".")

    # figure out cheapest/lowest slots
    low_slot_duration = conf['InkyPHAT']['LowSlotDuration']
    num_low_slots = int(2 * low_slot_duration)
    inky_data_only = [slot_data[tuple_idx] for slot_data in inky_data]
    low_slots_list = []
    for i in range(0, len(inky_data_only) - num_low_slots - 1):
        low_slots_list.append(sum(inky_data_only[i:i+num_low_slots])/num_low_slots)
    low_slots_start_idx = low_slots_list.index(min(low_slots_list))
    low_slots_average = format_str.format(min(low_slots_list))

    low_slots_start_time = str(datetime.strftime(pytz.utc.localize(
        datetime.strptime(inky_data[low_slots_start_idx][0], "%Y-%m-%d %H:%M:%S"),
        is_dst=None).astimezone(local_tz), "%H:%M"))

    print("Lowest " + str(low_slot_duration) + " hours: average " +
          low_slots_average + short_unit + "/kWh at " + low_slots_start_time + ".")

    min_slot = min(inky_data, key=lambda inky_data: inky_data[tuple_idx])
    min_slot_value = str(min_slot[tuple_idx])
    min_slot_time = str(datetime.strftime(pytz.utc.localize(datetime.strptime(
        min_slot[0], "%Y-%m-%d %H:%M:%S"), is_dst=None).astimezone(local_tz), "%H:%M"))

    print("Lowest value slot: " + min_slot_value + short_unit + " at " + min_slot_time + ".")

    # draw current price, in colour if it's high...
    # also highlight display with a coloured border if current price is high
    font = ImageFont.truetype(RobotoBlack, size=int(45 * font_scale_factor))
    message = format_str.format(inky_data[0][tuple_idx]) + short_unit
    x_pos = 4 * x_scale_factor
    y_pos = 8 * y_scale_factor

    slot_start = str(datetime.strftime(pytz.utc.localize(datetime.strptime(
        inky_data[0][0], "%Y-%m-%d %H:%M:%S"), is_dst=None).astimezone(
            local_tz), "%H:%M"))

    if inky_data[0][tuple_idx] > high_value:
        draw.text((x_pos, y_pos), message, inky_display.RED, font)
        inky_display.set_border(inky_display.RED)
        print("Current value from " + slot_start + ": " + message + " (High)")
    else:
        draw.text((x_pos, y_pos), message, inky_display.BLACK, font)
        inky_display.set_border(inky_display.WHITE)
        print("Current value from " + slot_start + ": " + message)

    # scale the y-axis
    selected_inky_data = inky_data[:data_duration*2]
    max_slot = max(selected_inky_data, key=lambda selected_inky_data: selected_inky_data[tuple_idx])
    max_slot_value = max_slot[tuple_idx]
    graph_y_unit = (inky_display.HEIGHT / 2.5) / max_slot_value

    # draw graph solid bars...
    # shift axis for negative prices
    if min_slot[tuple_idx] < 0:
        graph_bottom = (inky_display.HEIGHT + min_slot[1]
                        * graph_y_unit) - 13 * y_scale_factor
    else:
        graph_bottom = inky_display.HEIGHT - 13 * y_scale_factor

    i = 0
    for slot_data in inky_data:
        # draw the lowest slots in black and the highest in red/yellow

        if (i + 1) * graph_x_unit > 127 * x_scale_factor:
            break # don't scribble on the small text

        if conf['Mode'] == "agile_import" or conf['Mode'] == "carbon":
            if low_slots_start_idx <= i < low_slots_start_idx + num_low_slots:
                colour = inky_display.BLACK
            elif slot_data[tuple_idx] > high_value:
                colour = inky_display.RED
            else:
                colour = inky_display.WHITE

        if conf['Mode'] == "agile_export":
            if high_slots_start_idx <= i < high_slots_start_idx + num_high_slots:
                colour = inky_display.BLACK
            elif slot_data[tuple_idx] > high_value:
                colour = inky_display.RED
            else:
                colour = inky_display.WHITE

        bar_y_height = slot_data[tuple_idx] * graph_y_unit

        draw.rectangle(((i + 1) * graph_x_unit, graph_bottom,
                        (((i + 1) * graph_x_unit) - graph_x_unit),
                        (graph_bottom - bar_y_height)), colour)
        i += 1
    # graph solid bars finished

    # draw time info above current price...
    font = ImageFont.truetype(RobotoMedium, size=int(15 * font_scale_factor))
    message = descriptor + slot_start + "    " # trailing spaces prevent text clipping
    x_pos = 4 * x_scale_factor
    y_pos = 0 * y_scale_factor
    draw.text((x_pos, y_pos), message, inky_display.BLACK, font)

    mins_until_next_slot = ceil((pytz.utc.localize(datetime.strptime(
        inky_data[1][0], "%Y-%m-%d %H:%M:%S"), is_dst=None) - datetime.now(
            pytz.timezone("UTC"))).total_seconds() / 60)

    print(str(mins_until_next_slot) + " mins until next slot.")

    # draw next 3 slot times...
    font = ImageFont.truetype(RobotoMedium, size=int(15 * font_scale_factor))
    x_pos = 130 * x_scale_factor
    for i in range(3):
        message = "+" + str(mins_until_next_slot + (i * 30)) + ":    "
        # trailing spaces prevent text clipping
        y_pos = i * 18 * y_scale_factor + 3 * y_scale_factor
        draw.text((x_pos, y_pos), message, inky_display.BLACK, font)

    # draw next 3 slot prices...
    x_pos = 163 * x_scale_factor
    for i in range(3):
        message = format_str.format(inky_data[i+1][tuple_idx]) + short_unit + "    "
        # trailing spaces prevent text clipping
        y_pos = i * 18 * y_scale_factor + 3 * y_scale_factor
        if inky_data[i+1][tuple_idx] > high_value:
            draw.text((x_pos, y_pos), message, inky_display.RED, font)
        else:
            draw.text((x_pos, y_pos), message, inky_display.BLACK, font)

    # draw separator line...
    ypos = 5 * y_scale_factor + (3 * 18 * y_scale_factor)
    draw.line((130 * x_scale_factor, ypos, inky_display.WIDTH - 5, ypos),
              fill=inky_display.BLACK, width=2)

    # draw lowest slots info...
    x_pos = 130 * x_scale_factor
    y_pos = 10 * y_scale_factor + (3 * 18 * y_scale_factor)
    font = ImageFont.truetype(RobotoMedium, size=int(13 * font_scale_factor))



    if conf['Mode'] == "agile_import" or conf['Mode'] == "carbon":
        if '.' in str(low_slot_duration):
            lsd_text = str(low_slot_duration).rstrip('0').rstrip('.')
        else:
            lsd_text = str(low_slot_duration)

        draw.text((x_pos, y_pos), lsd_text + "h @" + low_slots_average + short_unit + "    ",
                  inky_display.BLACK, font)

        min_slot_timedelta = datetime.strptime(
            inky_data[low_slots_start_idx][0],
            "%Y-%m-%d %H:%M:%S") - datetime.strptime(inky_data[0][0], "%Y-%m-%d %H:%M:%S")

        y_pos = 16 * (y_scale_factor * 0.6) + (4 * 18 * y_scale_factor)

        if min_slot_timedelta.total_seconds() > 1800:
            draw.text((x_pos, y_pos), low_slots_start_time + "/" +
                      str(min_slot_timedelta.total_seconds() / 3600) +
                      "h    ", inky_display.BLACK, font)
        else:
            font = ImageFont.truetype(RobotoMedium, size=int(16 * font_scale_factor))
            draw.text((x_pos, y_pos), "NOW!", inky_display.RED, font)

    if conf['Mode'] == "agile_export":
        if '.' in str(high_slot_duration):
            hsd_text = str(high_slot_duration).rstrip('0').rstrip('.')
        else:
            hsd_text = str(high_slot_duration)

        draw.text((x_pos, y_pos), hsd_text + "h @",
                  inky_display.BLACK, font)

        if float(high_slots_average) > high_value:
            colour = inky_display.RED
        else:
            colour = inky_display.BLACK
        draw.text((x_pos + (30 * x_scale_factor), y_pos), high_slots_average + short_unit + "    ",
                  colour, font)

        max_slot_timedelta = datetime.strptime(
            inky_data[high_slots_start_idx][0],
            "%Y-%m-%d %H:%M:%S") - datetime.strptime(inky_data[0][0], "%Y-%m-%d %H:%M:%S")

        y_pos = 16 * (y_scale_factor * 0.6) + (4 * 18 * y_scale_factor)

        if max_slot_timedelta.total_seconds() > 1800:
            draw.text((x_pos, y_pos), high_slots_start_time + "/" +
                      str(max_slot_timedelta.total_seconds() / 3600) +
                      "h    ", inky_display.BLACK, font)
        else:
            font = ImageFont.truetype(RobotoMedium, size=int(16 * font_scale_factor))
            draw.text((x_pos, y_pos), "NOW!", inky_display.RED, font)

    # draw graph outline (last so it's over the top of everything else)
    i = 0
    for i, slot_data in enumerate(inky_data):
        colour = inky_display.BLACK
        bar_y_height = slot_data[tuple_idx] * graph_y_unit
        prev_bar_y_height = inky_data[i-1][tuple_idx] * graph_y_unit

        if (i + 1) * graph_x_unit > 127 * x_scale_factor: # don't scribble on the small text
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
    draw.line((0, graph_bottom, 126 * x_scale_factor, graph_bottom), inky_display.BLACK)

    # draw graph hour marker text... XXX FIXME XXX
    for i in range(2, data_duration, ceil(data_duration / 8)):
        colour = inky_display.BLACK
        font = ImageFont.truetype(RobotoMedium, size=int(10 * font_scale_factor))
        x_pos = i * graph_x_unit * 2 # it's half hour slots!!
        hours = datetime.strftime(datetime.now() + timedelta(hours=i), "%H")
        hours_w, hours_h = font.getsize(hours) # we want to centre the labels
        y_pos = graph_bottom + 1
        if x_pos + hours_w / 2 > 128 * x_scale_factor:
            break # don't draw past the end of the x axis
        draw.text((x_pos - hours_w / 2, y_pos + 1), hours + "  ", inky_display.BLACK, font)
        # and the tick marks for each one
        draw.line((x_pos, y_pos + 2 * y_scale_factor, x_pos, graph_bottom),
                  inky_display.BLACK)

    # draw average line...
    # extract just values from the list of tuples and put in descending order
    slot_data_list = sorted(list(zip(*inky_data))[tuple_idx], reverse=True)
    # now slice off the first (highest) 6 entries
    del slot_data_list[:6]
    # and calculate the mean
    average_slot_data = sum(slot_data_list) / len(slot_data_list)

    average_line_ypos = graph_bottom - average_slot_data * graph_y_unit

    for x_pos in range(0, int(126 * x_scale_factor)):
        if x_pos % 6 == 2: # repeat every 6 pixels starting at 2
            draw.line((x_pos, average_line_ypos, x_pos + 2, average_line_ypos),
                      inky_display.BLACK)

    # Flip orientation if option is set
    if conf['InkyPHAT']['DisplayOrientation'] == 'inverted':
        img=img.rotate(180)

    inky_display.set_image(img)
    inky_display.show()

def clear_display(conf: dict):
    """Determine what type of display is connected and
    use the appropriate method to clear it."""
    if conf['DisplayType'] == 'blinkt':

        import blinkt

        print('Clearing Blinkt! display...')
        blinkt.clear()
        blinkt.show()
        print('Done.')

    elif conf['DisplayType'] == 'inkyphat':

        from inky.auto import auto
        from inky.eeprom import read_eeprom
        from PIL import Image

        inky_eeprom = read_eeprom()
        if inky_eeprom is None:
            raise SystemExit('Error: Inky pHAT display not found')

        print('Clearing Inky pHAT display...')
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

        print('Done.')

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

def get_config(filename: str) -> dict:
    """
    Read config file and do some basic checks that we have what we need.
    If not, set sensible defaults or bail out.
    """
    try:
        config_file = open(filename, 'r')
    except FileNotFoundError as no_config:
        raise SystemExit('Unable to find ' + filename) from no_config

    try:
        _config = yaml.safe_load(config_file)
    except yaml.YAMLError as config_err:
        raise SystemExit('Error reading configuration: ' + str(config_err)) from config_err

    if 'DisplayType' not in _config:
        raise SystemExit('Error: DisplayType not found in ' + filename)

    if _config['DisplayType'] == 'blinkt':
        print('Blinkt! display selected.')

        conf_brightness = deep_get(_config, ['Blinkt', 'Brightness'])
        if not (isinstance(conf_brightness, int) and 5 <= conf_brightness <= 100):
            print('Misconfigured brightness value: ' + str(conf_brightness) +
                  '. Using default of ' + str(DEFAULT_BRIGHTNESS) + '.')
            _config['Blinkt']['Brightness'] = DEFAULT_BRIGHTNESS

        conf_slotsperpixel = deep_get(_config, ['Blinkt', 'SlotsPerPixel'])
        if not (isinstance(conf_slotsperpixel, int) and 1 <= conf_slotsperpixel <= 12):
            print('Misconfigured slots per pixel value: ' + str(conf_slotsperpixel) +
                  '. Using default of ' + str(DEFAULT_SLOTSPERPIXEL) + '.')
            _config['Blinkt']['SlotsPerPixel'] = DEFAULT_SLOTSPERPIXEL

        if len(_config['Blinkt']['Colours'].items()) < 2:
            raise SystemExit('Error: Less than two colour levels found in ' + filename)

    elif _config['DisplayType'] == 'inkyphat':
        print('Inky pHAT display selected.')

        if 'DisplayOrientation' not in _config['InkyPHAT']:
            _config['InkyPHAT']['DisplayOrientation'] = 'standard'
            print('Standard display orientation.')
        elif _config['InkyPHAT']['DisplayOrientation'] == 'standard':
            print('Standard display orientation.')
        elif _config['InkyPHAT']['DisplayOrientation'] == 'inverted':
            print('Inverted display orientation.')
        else:
            raise SystemExit('Error: Unknown display orientation found in ' + 
                  filename + ': ' + _config['InkyPHAT']['DisplayOrientation'])

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

        conf_dataduration = deep_get(_config, ['InkyPHAT', 'DataDuration'])
        if not (isinstance(conf_dataduration, (int)) and 12 <= conf_highprice <= 48):
            print('Data duration misconfigured: ' + str(conf_dataduration) +
                  ' (must be between 12 and 48 hours).' +
                  ' Using default of ' + str(DEFAULT_DATADURATION) + '.')
            _config['InkyPHAT']['DataDuration'] = DEFAULT_DATADURATION

    else:
        raise SystemExit('Error: unknown DisplayType ' + _config['DisplayType'] + ' in ' + filename)

    if 'Mode' not in _config:
        raise SystemExit('Error: Mode not found in ' + filename)

    if _config['Mode'] == 'agile_import':
        print('Working in Octopus Agile import mode.')

        if 'AgileCap' not in _config:
            raise SystemExit('Error: Agile cap not found in ' + filename)

        if _config['AgileCap'] == 35:
            print('Agile version set: 35p cap (pre July 2022)')
        elif _config['AgileCap'] == 55:
            print('Agile version set: 55p cap (July 2022 onwards)')
        elif _config['AgileCap'] == 78:
            print('Agile version set: 78p cap (August 2022 onwards)')
        elif _config['AgileCap'] == 100:
            print('Agile version set: £1 cap, new formula (October 2022 only)')
        elif _config['AgileCap'] == 101:
            print('Agile version set: £1 cap, new-new formula (current)')
        else:
            raise SystemExit('Error: Agile cap of ' + str(_config['AgileCap']) + ' refers to an unknown tariff.')

    elif _config['Mode'] == 'agile_export':
        print('Working in Octopus Agile export mode.')
    elif _config['Mode'] == 'carbon':
        print('Working in carbon intensity mode.')
    elif _config['Mode'] == 'tracker':
        print('Working in Octopus Tracker mode.')
    else:
        raise SystemExit('Error: Unknown mode found in ' + filename + ': ' + _config['Mode'])

    if 'DNORegion' not in _config:
        raise SystemExit('Error: DNORegion not found in ' + filename)

    return _config
