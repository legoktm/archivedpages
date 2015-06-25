#!/usr/bin/env python

# Authors: Legoktm, Betacommand
# License: MIT License

import datetime
import functools
import logging
import mwparserfromhell
import pywikibot
import re
import requests
import time

site = pywikibot.Site('en', 'wikipedia')

archive_range_days = 365 * 7
archive_range_sec = 60 * 60 * 24 * archive_range_days


@functools.lru_cache()
def get_template_redirect_names(name):
    t = pywikibot.Page(site, 'Template:' + name)
    s = set(p.title(withNamespace=False) for p in t.getReferences(redirectsOnly=True, namespaces=[10]))
    s.add(name)
    return tuple(s)

def get_url(url, wp_ts=None):
    print('checking archive.org...')
    params = {'url': str(url).strip()}
    if wp_ts:
        params['timestamp'] = wp_ts
    url = 'https://archive.org/wayback/available'
    print(url, params)
    r = requests.get(url, params=params)
    try:
        j = r.json()
    except ValueError:
        print('not valid json')
        return False
    if not j['archived_snapshots']:
        #print j
        print('no archived snapshots?')
        return False
    #print j
    closest = j['archived_snapshots']['closest']
    if str(not closest['status']).startswith('2'):
        print('not a 2XX status code')
        return False
    # now check that it's not too old
    if wp_ts:
        ts = closest['timestamp']
        IA_TS = pywikibot.Timestamp.fromtimestampformat(ts)
        WP_TS = pywikibot.Timestamp.fromtimestampformat(wp_ts)
        diff = abs((WP_TS - IA_TS).total_seconds())
        if diff > archive_range_sec:
            print('out of range - %s' % (diff/(60*60*24)))
            return False
    print('RETURNING!')
    #print r.text
    return closest['url'], closest['timestamp']


def prettify_archive_timestamp(ts):
    return pywikibot.Timestamp.fromtimestampformat(ts).strftime('%d %B %Y')


def archive_page(text):
    code = mwparserfromhell.parse(text)
    for tag in code.filter_tags():
        if tag.tag == 'ref' and tag.contents is not None:
            print(repr(tag.contents))
            found_cite_web = 0
            dead_link_temp = None
            cite_web_temp = None
            for t in tag.contents.filter_templates(recursive=True):
                if t.name.matches(get_template_redirect_names('Cite web')):
                    cite_web_temp = t
                    found_cite_web += 1
                    if not t.has_param('url'):
                        continue
                    if t.has_param('archiveurl'):
                        continue
                    url = t.get('url').value
                    ts = check_accessdate(str(t))
                    if ts:
                        ts = ts.totimestampformat()
                    res = get_url(url, ts)
                    if not res:
                        continue

                    t.add('archiveurl', res[0])
                    t.add('deadurl', 'no')
                    t.add('archivedate', prettify_archive_timestamp(res[1]))
                elif t.name.matches(get_template_redirect_names('Dead link')):
                    dead_link_temp = t
            if found_cite_web > 1:
                # Eh, wtf. Skip
                continue
            if cite_web_temp and dead_link_temp:
                cite_web_temp.get('deadurl').value = 'yes'
                code.remove(dead_link_temp)

    return str(code)


def check_accessdate(refs):
    """
    @return pywikibot.Timestamp
    """
    #refs = ' '.join(self.ref_where_used()).replace('&nbsp;','-').replace(')',' ').replace('(',' ')
    #print refs
    accessdate = re.search('\|[^\|]*accessdate\s*\=\s*(?P<here>.*?)(\||}})',refs,re.I)
    if not accessdate and re.search('(Retrieved|accessed) (on )?(?P<here>.*?)(\.|\<)',refs,re.I):
        accessdate = re.search('(Retrieved|accessed) (on )?(?P<here>.*?)(\.|\<)',refs,re.I)
    """
    if not accessdate:
        try:
            accessdate = time.strftime('%Y.%m.%d',tool_kit.blame(self.link,self.page))
        except:
            accessdate = None
        # log('No accessdate for '+self.link+' could be found')
        # try:
            # return self.query_wikiblame()
        # except:
            # datehigh = time.strftime('%Y%m%d%H%M%S') #make into Internet archive date
            # datelow = time.strftime('%Y%m%d%H%M%S')
            # log('Accessdate range for '+self.link+' was '+datelow+'-'+datehigh)
            # return datelow+'-'+datehigh
    """
    if accessdate:
        try:
            accessdate = accessdate.group('here').strip()
        except:
            pass
        #log('Parsed accessdate for '+self.link+ ' was '+accessdate)
        accessdate = re.split('[\,\-\.\;\s/]+',accessdate)  # Split the acccessdate into chunks.

        month = None
        year = None
        day = None
        tryagain=accessdate
        accessdate.sort()
        accessdate.reverse()  # Puts strings first
        data = {'MAR': '03', 'FEB': '02', 'AUG': '08', 'SEP': '09', 'APR': '04', 'JUN': '06', 'JUL': '07', 'JAN': '01', 'MAY': '05', 'NOV': '11', 'DEC': '12', 'OCT': '10'}
        for date in accessdate:
            if date.upper()[:3] in data.keys() and not month:
                month = data[date.upper()[:3]]
                # Makes so anycase, abbreviation or full version of a month is identified as month.
            elif re.match('\d{4}', date) and not year:
                year = date  # 4 digits is obviously a year.

            elif re.match('\d+', date):
                if int(date) > 12:
                    day = date  # If more then 12, it is obviously a day.
                elif month and (day is None):
                    day = date  # If there is a month it must be a day.
                elif day and (month is None):
                    month = date  # Ditto

        if None in (day, month, year):
            year = year
            for date in tryagain:
                if len(date) > 2:
                    continue
                elif not month:
                    month = date
                else:
                    day = date

        if len(day) == 1:
            day = '0' + day
        if len(month) == 1:
            month = '0' + month
        try:
            date = time.strptime(str(year)+str(month)+str(day), '%Y%m%d')  # make into time.strctime
        except:
            return None
#            date = time.gmtime()  # make into time.strctime
        date = time.mktime(date)
        #print repr(date)
        return pywikibot.Timestamp.utcfromtimestamp(float(date))


def test():
    pg = pywikibot.Page(site, '174th Tunnelling Company')
    text = pg.get()
    new = archive_page(text)
    pywikibot.showDiff(text, new)
    #pg.put(new, 'Bot: adding links to archived copies of references')

if __name__ == '__main__':
    #print(get_template_redirect_names())
    test()
