from datetime import timedelta
import json
import shutil
from django.test import TestCase
from django.test.utils import override_settings
from django.utils.timezone import now

from alert.api.management.commands.cl_make_bulk_data import Command
from alert.lib.test_helpers import SolrTestCase
from alert.search.models import Docket, Citation, Court, Document
from alert.scrapers.management.commands.cl_scrape_oral_arguments import \
    Command as OralArgumentCommand
from alert.scrapers.test_assets import test_oral_arg_scraper
from alert.search import tasks


class BulkDataTest(TestCase):
    fixtures = ['test_court.json']
    tmp_data_dir = '/tmp/bulk-dir/'

    def setUp(self):
        c1 = Citation(case_name=u"foo")
        c1.save(index=False)
        docket = Docket(
            case_name=u'foo',
            court=Court.objects.get(pk='test'),
        )
        docket.save()
        # Must be more than a year old for all tests to be runnable.
        last_month = now().date() - timedelta(days=400)
        self.doc = Document(
            citation=c1,
            docket=docket,
            date_filed=last_month
        )
        self.doc.save(index=False)

        # Scrape the audio "site" and add its contents
        site = test_oral_arg_scraper.Site().parse()
        OralArgumentCommand().scrape_court(site, full_crawl=True)

    def tearDown(self):
        Document.objects.all().delete()
        Docket.objects.all().delete()
        Citation.objects.all().delete()
        shutil.rmtree(self.tmp_data_dir)

    @override_settings(BULK_DATA_DIR=tmp_data_dir)
    def test_make_all_bulk_files(self):
        """Can we successfully generate all bulk files?"""
        Command().execute()


class CoverageAPITest(SolrTestCase):
    fixtures = ['test_court.json', 'court_data.json']

    def setUp(self):
        """Run the normal set up routine for SolrTestCase, but swap a few of
        the courts at the end.
        """
        super(CoverageAPITest, self).setUp()

        ca1 = Court.objects.get(pk='ca1')
        self.docs[0].docket.court = ca1
        self.docs[0].docket.save()

        tasks.add_or_update_doc(1, force_commit=True)

    def test_coverage_sans_query_and_all_courts(self):
        r = self.client.get('/api/rest/v2/coverage/all/')
        j = json.loads(r.content)
        self.assertEqual(
            j['annual_counts']['2013'],
            2,
        )
        self.assertEqual(len(j['annual_counts']), 9)
        self.assertEqual(j['total'], 3)

    def test_coverage_sans_query_and_with_specific_court(self):
        r = self.client.get('/api/rest/v2/coverage/ca1/')
        j = json.loads(r.content)
        self.assertEqual(
            j['annual_counts']['2013'],
            1,
        )
        self.assertEqual(len(j['annual_counts']), 1)
        self.assertEqual(j['total'], 1)

    def test_coverage_with_query_and_all_courts(self):
        r = self.client.get('/api/rest/v2/coverage/all/?q=supreme')
        j = json.loads(r.content)
        self.assertEqual(
            j['annual_counts']['2013'],
            1,
        )
        self.assertEqual(
            j['annual_counts']['2005'],
            1,
        )
        self.assertEqual(len(j['annual_counts']), 9)
        self.assertEqual(j['total'], 2)

    def test_coverage_with_query_and_specific_court(self):
        r = self.client.get('/api/rest/v2/coverage/ca1/?q=water')
        j = json.loads(r.content)
        self.assertEqual(
            j['annual_counts']['2013'],
            1,
        )
        self.assertEqual(len(j['annual_counts']), 1)
        self.assertEqual(j['total'], 1)
