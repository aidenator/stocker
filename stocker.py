#!/usr/bin/env python3
import curses
from curses import panel
import requests

my_symbols = ["PLTR","XOM","VTSAX","VIGAX","GC=F","BTC-USD", "GME"]
yahoo_fields = ["symbol","regularMarketPrice","regularMarketChange","regularMarketChangePercent"]
yahoo_url = "https://query1.finance.yahoo.com/v7/finance/quote?lang=en-US&region=US&corsDomain=finance.yahoo.com"
yahoo_chart_url = "https://query1.finance.yahoo.com/v8/finance/chart/"
header = "Symbol  |  Price $ | Change (%)\n" \
         "-------------------------------\n"

# Do the GET and retrieve raw JSON
def get_json(url, params=None):
    r = requests.get(url, params=params, stream=True)
    r.raise_for_status()
    return r.json()

# Get historic data for making charts
# Period values = 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
# Interval values = 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo
# Ex URL: https://query1.finance.yahoo.com/v8/finance/chart/XOM?range=1y&interval=1mo
def get_chart_data(symbol, period, interval):
    params = {}
    params['range'] = period
    params['interval'] = interval
    url = yahoo_chart_url + symbol
    raw = get_json(url, params=params)

    return raw

# Get the basic stock data for all symbols
def get_stock_data(symbols, fields):
    params = {}
    params['symbols'] = ",".join(symbols)
    params['fields'] = ",".join(fields)
    raw = get_json(yahoo_url, params=params)

    rows = []
    for result in raw["quoteResponse"]["result"]:
        row = {
            "name": result['symbol'],
            "price": result['regularMarketPrice'],
            "change": result['regularMarketChange'],
            "change_per": result['regularMarketChangePercent']
        }
        rows.append(row)

    return rows

# Returns a big string with an overview of all stocks
# Home page of the program
def overview(data):
    rows = ""
    for result in data["quoteResponse"]["result"]:
        symbol = f"{result['symbol']}"
        price = f"{result['regularMarketPrice']:6.2f}"
        change = f"{result['regularMarketChange']:6.2f}"
        change_per = f"{result['regularMarketChangePercent']:.2f}"
        rows += f"{symbol: <7} | {price:>8} | {change:>8} ({change_per}%)"
        rows += "\n"

    return header + rows

def shrink_array(array, new_size):
    new_array = []
    orig_len = len(array)

    # No shrinking to be done
    if orig_len <= new_size:
        return array

    interval = -(-orig_len // new_size) # Some crazy black magic to get the ceiling of division

    for i,val in enumerate(array):
        if i % interval == 0:
            new_array.append(val)

    # We always want the final value included
    if len(new_array) == new_size:
        new_array.pop()

    new_array.append(array[orig_len - 1])

    return new_array

#"open": [33.36,30.02,27.98,24.98,27.02]
#"close":[31.90,27.84,27.07,25.17,29.0]
def print_chart(w, data, chart_height, scr_width):
    curses.init_pair(1, curses.COLOR_RED, 0)
    curses.init_pair(2, curses.COLOR_GREEN, 0)
    row = 0
    chart_char = "■"
    chart_char = "█"

    # The data we were expecting was not in the dictionary
    if "close" not in data['chart']['result'][0]['indicators']['quote'][0] or "open" not in data['chart']['result'][0]['indicators']['quote'][0]:
        error_text = "Couldn't get data for chart"
        w.addstr(chart_height // 2, row, error_text, 0)
        return

    closes = data['chart']['result'][0]['indicators']['quote'][0]['close']
    opens = data['chart']['result'][0]['indicators']['quote'][0]['open']
    name = data['chart']['result'][0]['meta']['symbol']
    interval = data['chart']['result'][0]['meta']['dataGranularity']
    period = data['chart']['result'][0]['meta']['range']

    # Scrub through data, sometimes Yahoo sends in null's or zeroes
    opens = [item for item in opens if item is not None and item > 0]
    closes = [item for item in closes if item is not None and item > 0]

    # Shrink arrays to fit within screen width
    closes = shrink_array(closes, scr_width - 10)
    opens = shrink_array(opens, scr_width - 10)

    # Get maxes and mins for upper/lower boundaries of the chart
    min_close = min(closes)
    max_close = max(closes)
    min_open = min(opens)
    max_open = max(opens)
    max_val = max(max_close, max_open)
    min_val = min(min_close, min_open)

    if max_val == min_val:
        error_text = "Not enough granularity for a chart"
        w.addstr(chart_height // 2, row, error_text, 0)
        return

    # For each datapoint, calculate the height on the chart.
    # Remove offset of min_val since we want to focus on all points above it.
    # Find the ratio of this value to max value.
    #Finally, multiply by the chart height.
    for o,c in zip(opens,closes):
        y_open = int((o - min_val) / (max_val - min_val) * chart_height)
        y_close = int((c - min_val) / (max_val - min_val) * chart_height)

        bigger = max(y_open, y_close)
        smaller = min(y_open, y_close)
        # For each column on the chart, fill in squares if between y_open and y_close
        for i in range(chart_height):
            if i >= smaller and i <= bigger:
                # Color losses red, and gains green
                color = curses.color_pair(1) if y_close < y_open else curses.color_pair(2)
                w.addstr(chart_height - 1 - i, row, chart_char, color)

        row += 1

    # Print the highest and lowest values
    w.addstr(0, len(opens), f"${max_val:.2f}")
    w.addstr(chart_height-1, len(opens), f"${min_val:.2f}")

    # Print extra details at bottom
    w.addstr(chart_height, 0, f"{name} --- Range:{period} Interval:{interval}")

def format_row(symbol, width):
    columns = [{"title":"Symbol ","key":"name","width":8,"form":"{}"},
               {"title":"  Price $ ","key":"price","width":10,"form":"{:6.2f}"},
               {"title":"  Change  ","key":"change","width":10,"form":":6.2f"},
               {"title":" (%) ","key":"change_per","width":6,"form":":3.2f"},]
    ret = ""

    for col in columns:
        width -= col['width'] - 1
        if width < 0:
            break

        key = col['key']
        val = symbol[key]
        ret += col['form'].format(val) + "|"

    return ret

class chart_menu(object):

    def __init__(self, symbol, stdscreen):
        self.window = stdscreen.subwin(0, 0)
        self.window.keypad(1)
        self.panel = panel.new_panel(self.window)
        self.panel.hide()
        panel.update_panels()

        self.position = 0
        self.symbol = symbol
        self.items = []
        self.items.append(["1d", "2m"])
        self.items.append(["1wk", "30m"])
        self.items.append(["1mo", "90m"])
        self.items.append(["1y", "1wk"])
        self.items.append(["5y", "1mo"])

    def navigate(self, n):
        self.position += n
        if self.position < 0:
            self.position = 0
        elif self.position >= len(self.items):
            self.position = len(self.items) - 1

    def display(self):
        height, width = self.window.getmaxyx()
        # Must shrink chart_height if it won't fit with the menu height
        chart_height = min(20, height - len(self.items) - 1)
        self.panel.top()
        self.panel.show()
        self.window.clear()

        # Print the chart of the last stored selection
        data = get_chart_data(self.symbol, self.items[self.position][0], self.items[self.position][1]);
        print_chart(self.window, data, chart_height, width)

        while True:
            self.window.refresh()
            curses.doupdate()
            for index, item in enumerate(self.items):
                if index == self.position:
                    mode = curses.A_REVERSE
                else:
                    mode = curses.A_NORMAL

                msg = "%d. %s" % (index, item)
                self.window.addstr(chart_height + 1 + index, 1, msg, mode)

            key = self.window.getch()

            if key in [curses.KEY_ENTER, ord("\n")]:
                self.window.clear()
                data = get_chart_data(self.symbol, self.items[self.position][0], self.items[self.position][1]);
                print_chart(self.window, data, chart_height, width)

            elif key == curses.KEY_UP or key == ord("k"):
                self.navigate(-1)

            elif key == curses.KEY_DOWN or key == ord("j"):
                self.navigate(1)

            elif key == 27 or key == ord("q"):
                break

        self.window.clear()
        self.panel.hide()
        panel.update_panels()
        curses.doupdate()

class Menu(object):
    def __init__(self, symbols, stdscreen):
        self.window = stdscreen.subwin(0, 0)
        self.window.keypad(1)
        self.panel = panel.new_panel(self.window)
        self.panel.hide()
        panel.update_panels()

        self.position = 0

        self.symbols = get_stock_data(symbols, yahoo_fields)
        self.charts = []
        for symbol in self.symbols:
            self.charts.append(chart_menu(symbol['name'], stdscreen))

    def navigate(self, n):
        self.position += n
        if self.position < 0:
            self.position = 0
        elif self.position >= len(self.symbols):
            self.position = len(self.symbols) - 1

    def display(self):
        self.panel.top()
        self.panel.show()
        self.window.clear()

        while True:
            self.window.refresh()
            curses.doupdate()
            height, width = self.window.getmaxyx()

            self.window.addstr(0,0,header,0)

            #TODO: Add another get_stock_data() here

            for index, symbol in enumerate(self.symbols):
                if index == self.position:
                    mode = curses.A_REVERSE
                else:
                    mode = curses.A_NORMAL

                msg = format_row(symbol, width)
                #msg = "%d. %s" % (index, symbol['name'])
                self.window.addstr(2 + index, 1, msg, mode)

            key = self.window.getch()

            if key in [curses.KEY_ENTER, ord("\n")]:
                self.charts[self.position].display()

            elif key == curses.KEY_UP or key == ord("k"):
                self.navigate(-1)

            elif key == curses.KEY_DOWN or key == ord("j"):
                self.navigate(1)

            elif key == 27 or key == ord("q"):
                break

        self.window.clear()
        self.panel.hide()
        panel.update_panels()
        curses.doupdate()


class MyApp(object):
    def __init__(self, stdscreen):
        self.screen = stdscreen
        curses.curs_set(0)

        main_menu = Menu(my_symbols, self.screen)
        main_menu.display()


if __name__ == "__main__":
    curses.wrapper(MyApp)

