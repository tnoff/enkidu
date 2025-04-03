from datetime import date, datetime
from re import compile as re_compile
from re import match

from bs4 import BeautifulSoup
from requests import get as requests_get


WIKI_BASE_URL = 'https://en.wikipedia.org'
FIRST_FIGHT_SUFFIX = '/wiki/UFC_on_ESPN:_Luque_vs._dos_Anjos'
# When UFC adopted new rules, most logical place to stop for now
STOP_PAGE = '/wiki/2000_in_UFC#UFC_27:_Ultimate_Bad_Boyz'

FIGHT_TABLE_EXPECTED_KEYS = [
    'weight_class',
    'fighter_one',
    None, # def.
    'fighter_two',
    'method',
    'round',
    'time',
    'notes',
]

FIGHTER_KEYS = [
    'fighter_one',
    'fighter_two',
]

WEIGHT_MAPPING = {
    'heavyweight': 265,
    'light heavyweight': 205,
    'middleweight': 185,
    'welterweight': 170,
    'lightweight': 155,
    'featherweight': 145,
    'bantamweight': 135,
    'flyweight': 125,
    "women's strawweight": 115,
    "women's flyweight": 125,
    "women's bantamweight": 135,
    "women's featherweight": 145,
    # Some fights don't list catchweight weight
    'catchweight': 0,
}

CATCHWEIGHT_REGEX = r'(women\'s )?catchweight \((?P<weight>[0-9]+)'



class SkipSuffix(Exception):
    pass

class InvalidWeight(Exception):
    pass

class RequestException(Exception):
    pass

class StopLookingException(Exception):
    pass

def __process_card(self, suffix, end_date=date.today()):
    if suffix == STOP_PAGE:
        raise StopLookingException('New rules implemented after this card')

    req = requests_get(f'{WIKI_BASE_URL}{suffix}', timeout=60)
    if req.status_code != 200:
        raise RequestException(f'Unable to get fight information {suffix}')


    soup = BeautifulSoup(req.text, 'html.parser')

    title = soup.find('title').text.replace(' - Wikipedia', '')
    # Some pages are within larger pages, shown by a #
    # If we see this, use the strainer
    multi_pages = False
    event_count = -1
    if '#' in suffix:
        multi_pages = True
        spans = soup.find_all('span', class_='mw-headline')
        for span in spans:
            if 'vs.' in span.get('id').lower():
                event_count += 1
            if span.get('id') == suffix.split('#')[1]:
                title = span.text
                break
    else:
        event_count = 0
        soup = BeautifulSoup(req.text, 'html.parser')

    # Find previous event and next event
    event_chronoloy = soup.find_all('th', string=re_compile('Event chronology'))[event_count]
    event_table = event_chronoloy.parent.next_sibling.find('table')
    sections = event_table.find_all('td')
    previous_href = sections[0].find('a')['href']
    next_href = sections[2].find('a')['href']

    # Make sure the date is not in the future
    date_box = soup.find_all('th', {'scope': 'row'}, string=re_compile('Date'),)[event_count]
    try:
        fight_date_text = date_box.find_next('td').find_next('span', class_='published').text
    except AttributeError:
        # No span
        fight_date_text = date_box.find_next('td').text

    if 'cancelled' in fight_date_text.lower():
        return None, None, [], previous_href, next_href
    if '[' in fight_date_text:
        fight_date_text = fight_date_text.split('[')[0]
    try:
        fight_date = datetime.strptime(fight_date_text, '%B %d, %Y').date()
    except ValueError:
        try:
            fight_date = datetime.strptime(fight_date_text, '%d %B %Y').date()
        except ValueError:
            fight_date = datetime.strptime(fight_date_text, '%Y-%m-%d').date()
    if fight_date >= end_date:
        raise SkipSuffix(f'Skipping suffix {suffix}')

    # Find results table
    results_title = soup.find_all('span', id=re_compile('Results'))[event_count]
    fight_table = results_title.find_next('table')

    is_main_card = True

    all_fights = []
    for row in fight_table.find_all('tr'):
        columns = row.find_all('th')
        # Check for header that says main or prelim card
        if len(columns) == 1:
            is_main_card = 'main' in columns[0].text.lower()
            continue
        fight_data = {
            'is_main_card' : is_main_card,
        }
        for (count, column) in enumerate(row.find_all('td')):
            # Ignore extra keys
            if count >= len(FIGHT_TABLE_EXPECTED_KEYS):
                continue
            if FIGHT_TABLE_EXPECTED_KEYS[count] is None:
                continue
            # If fighter, keep name cased, otherwise lower
            text = column.text.strip()
            if FIGHT_TABLE_EXPECTED_KEYS[count] not in FIGHTER_KEYS:
                text = text.lower()
            # Remove champion string from name
            if FIGHT_TABLE_EXPECTED_KEYS[count] in FIGHTER_KEYS:
                text = text.replace(' (c)', '').replace(' (ic)', '')
            fight_data[FIGHT_TABLE_EXPECTED_KEYS[count]] = {
                'text': text,
            }
            # Find hrefs if any
            try:
                href = column.find('a')['href']
                fight_data[FIGHT_TABLE_EXPECTED_KEYS[count]]['href'] = href
            except TypeError:
                pass
        # If data not full, just skip
        if len(fight_data.keys()) < 2:
            continue
        try:
            weight = fight_data['weight_class']['text'].lower().replace('’', "'")
            weight = WEIGHT_MAPPING[weight]
        except KeyError:
            m = match(CATCHWEIGHT_REGEX, weight)
            if not m:
                raise InvalidWeight(f'Invalid weight {weight}') #pylint: disable=raise-missing-from
            weight = m.group('weight')
        fight_data['weight_class']['text'] = weight
        all_fights.append(fight_data)


    return title, fight_date, all_fights, previous_href, next_href

def handle(self, *args, **options):
    pending_pages = set([FIRST_FIGHT_SUFFIX])
    processed_pages = set([])

    while True:
        new_pages = set([])
        for pending in pending_pages:
            try:
                print(f'Processing page {pending}')
                try:
                    fight_title, fight_date, all_fights, previous_href, next_href = self.__process_card(pending)
                except StopLookingException:
                    continue
                processed_pages.add(pending)
                new_pages.add(previous_href)
                new_pages.add(next_href)
                if fight_title is None:
                    continue
                event, created = Event.objects.get_or_create(
                    name=fight_title,
                    date=fight_date,
                    stub=pending,
                )
                if not created:
                    continue
                for fight in all_fights:
                    fighter_one, _created = Fighter.objects.get_or_create(
                        name=fight['fighter_one']['text'],
                        stub=fight['fighter_one'].get('href', None),
                    )
                    fighter_two, _created = Fighter.objects.get_or_create(
                        name=fight['fighter_two']['text'],
                        stub=fight['fighter_two'].get('href', None),
                    )
                    time_split = fight['time']['text'].split(':')
                    # No contest or something else
                    rounds = fight['round']['text']
                    if time_split[0] == '':
                        time_seconds = 0
                        rounds = 0
                    else:
                        time_seconds = int(time_split[0]) * 60 + int(time_split[1])
                    # Catch edge case with no notes
                    try:
                        notes = fight['notes']['text']
                    except KeyError:
                        notes = ''
                    fight, _created = Fight.objects.get_or_create(
                        rounds=int(rounds),
                        method=fight['method']['text'],
                        weight=int(fight['weight_class']['text']),
                        is_main_card=fight['is_main_card'],
                        notes=notes,
                        time=time_seconds,
                        event=event,
                    )
                    fight.fighters.add(fighter_one)
                    fight.fighters.add(fighter_two)
                    fight.save()
            except SkipSuffix:
                processed_pages.add(pending)
            sleep(1)
        new_pages = new_pages - processed_pages
        pending_pages = pending_pages - processed_pages - set([STOP_PAGE])
        print(f'New pages found {new_pages}')
        pending_pages = pending_pages.union(new_pages)
        if len(pending_pages) == 0:
            print('No more pending pages, exiting')
            break