from datetime import date

from django.core.management import call_command
from django.test import TestCase

import httpretty

from backend.constants import WIKI_BASE_URL, FIRST_FIGHT_SUFFIX
from backend.data import dos_anjos, full_page
from backend.models import Event, Fighter, Fight


class CommandsTestCase(TestCase):
    @httpretty.activate(verbose=True, allow_net_connect=False)
    def test_backfill_data(self):
        args = []
        opts = {}
        httpretty.register_uri(
            httpretty.GET,
            f'{WIKI_BASE_URL}{FIRST_FIGHT_SUFFIX}',
            body=dos_anjos.TEXT,
        )
        httpretty.register_uri(
            httpretty.GET,
            f'{WIKI_BASE_URL}/wiki/2013_in_UFC#UFC_on_FX:_Belfort_vs._Bisping',
            body=full_page.TEXT,
        )
        call_command('backfill_data', *args, **opts)
        self.assertEqual(Event.objects.count(), 2)
        self.assertEqual(Fighter.objects.count(), 48)
        self.assertEqual(Fight.objects.count(), 24)
        self.assertEqual(Fight.objects.filter(is_main_card=True).count(), 10)

    def test_generate_combo(self):
        # Two fighters we should generate a combo for
        rusty = Fighter.objects.create(name='Rusty Shackleford')
        gribble = Fighter.objects.create(name='Dale Gribble')

        # Generate some fights
        hank = Fighter.objects.create(name='Hank Hill')
        event1 = Event.objects.create(name='Brawl in Harlen I', date=date(2011, 1, 1), stub='brawlinharlenI')
        fight1 = Fight.objects.create(rounds=1, weight=155, method='tko', notes='', is_main_card=True, time=120, event=event1)
        fight1.fighters.add(rusty)
        fight1.fighters.add(hank)
        boomhower = Fighter.objects.create(name='Boomhower')
        john = Fighter.objects.create(name='John Redcorn')
        fight2 = Fight.objects.create(rounds=1, weight=155, method='tko', notes='', is_main_card=True, time=60, event=event1)
        fight2.fighters.add(boomhower)
        fight2.fighters.add(john)
        
        event2 = Event.objects.create(name='Brawl in Harlen II', date=date(2011, 2, 1), stub='brawlinharlenII')
        fight3 = Fight.objects.create(rounds=1, weight=155, method='tko', notes='', is_main_card=False, time=5, event=event2)
        fight3.fighters.add(hank)
        fight3.fighters.add(boomhower)

        fight4 = Fight.objects.create(rounds=1, weight=155, method='tko', notes='', is_main_card=False, time=5, event=event2)
        fight4.fighters.add(john)
        fight4.fighters.add(gribble)