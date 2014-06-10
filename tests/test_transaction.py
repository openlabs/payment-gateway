# -*- coding: utf-8 -*-
'''
    Payment Transaction

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Ltd.
    :license: BSD, see LICENSE for more details
'''
import os
import sys
DIR = os.path.abspath(os.path.normpath(os.path.join(
    __file__, '..', '..', '..', '..', '..', 'trytond'
)))
if os.path.isdir(DIR):
    sys.path.insert(0, os.path.dirname(DIR))
import unittest
from decimal import Decimal
from datetime import date

import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, DB_NAME, USER, CONTEXT
from trytond.transaction import Transaction
from trytond.pyson import Eval


class TestPaymentTransaction(unittest.TestCase):
    """
    Test Payment Transaction
    """

    def setUp(self):
        """
        Setup data used in tests
        """
        trytond.tests.test_tryton.install_module('payment_gateway')

        self.PaymentTransaction = POOL.get('payment_gateway.transaction')
        self.PaymentProfile = POOL.get('party.payment_profile')
        self.Party = POOL.get('party.party')
        self.Currency = POOL.get('currency.currency')
        self.Company = POOL.get('company.company')
        self.User = POOL.get('res.user')
        self.Country = POOL.get('country.country')
        self.Sequence = POOL.get('ir.sequence')
        self.Account = POOL.get('account.account')
        self.EmailQueue = POOL.get('email.queue')

    def _create_coa_minimal(self, company):
        """Create a minimal chart of accounts
        """
        AccountTemplate = POOL.get('account.account.template')
        Account = POOL.get('account.account')

        account_create_chart = POOL.get(
            'account.create_chart', type="wizard")

        account_template, = AccountTemplate.search(
            [('parent', '=', None)]
        )

        session_id, _, _ = account_create_chart.create()
        create_chart = account_create_chart(session_id)
        create_chart.account.account_template = account_template
        create_chart.account.company = company
        create_chart.transition_create_account()

        receivable, = Account.search([
            ('kind', '=', 'receivable'),
            ('company', '=', company),
        ])
        payable, = Account.search([
            ('kind', '=', 'payable'),
            ('company', '=', company),
        ])
        create_chart.properties.company = company
        create_chart.properties.account_receivable = receivable
        create_chart.properties.account_payable = payable
        create_chart.transition_create_properties()

    def _create_gateway(self):
        """
        A helper function that creates a gateway
        """
        PaymentGateway = POOL.get('payment_gateway.gateway')
        Journal = POOL.get('account.journal')

        today = date.today()

        sequence, = self.Sequence.create([{
            'name': 'PM-%s' % today.year,
            'code': 'account.journal',
            'company': self.company.id
        }])

        self.account_cash, = self.Account.search([
            ('kind', '=', 'other'),
            ('name', '=', 'Main Cash'),
            ('company', '=', self.company.id)
        ])

        self.cash_journal, = Journal.create([{
            'name': 'Cash Journal',
            'code': 'cash',
            'type': 'cash',
            'credit_account': self.account_cash.id,
            'debit_account': self.account_cash.id,
            'sequence': sequence.id,
        }])

        gateway = PaymentGateway(
            name='Test Gateway',
            journal=self.cash_journal,
            provider='self',
            method='manual',
        )
        gateway.save()

        return gateway

    def setup_defaults(self):
        """
        Setup data for testing
        """
        with Transaction().set_context({'company': None}):

            self.company_party, = self.Party.create([{
                'name': 'Test Company'
            }])

        self.currency = self.Currency(
            name='Euro', symbol=u'€', code='EUR',
        )
        self.currency.save()

        self.company, = self.Company.create([{
            'party': self.company_party.id,
            'currency': self.currency
        }])

        self.User.write(
            [self.User(USER)], {
                'main_company': self.company.id,
                'company': self.company.id
            }
        )

        self.country, = self.Country.create([{
            'name': 'India',
            'code': 'IN'
        }])

        self._create_coa_minimal(company=self.company.id)

        with Transaction().set_context({'company': self.company.id}):
            self.party, = self.Party.create([{
                'name': 'Test Party',
                'addresses': [('create', [{
                    'name': 'Test Party',
                    'party': Eval('id'),
                    'city': 'Noida',
                    'country': self.country.id,
                }])],
                'contact_mechanisms': [('create', [
                    {'type': 'email', 'value': 'party@ol.in'},
                ])],
            }])

        self.gateway = self._create_gateway()

    def test0010_check_email_notification(self):
        """
        Test transaction email notification
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()

            payment_transaction, = self.PaymentTransaction.create([{
                'description': "Some description",
                'party': self.party,
                'address': self.party.addresses[0],
                'amount': Decimal('100'),
                'currency': self.currency.id,
                'date': date.today(),
                'company': self.company,
                'gateway': self.gateway,
                'state': 'posted',
            }])
            payment_transaction.save()

            payment_transaction.send_email_notification()

            # Check if no email was sent if party has no email address
            self.assertEqual(len(self.EmailQueue.search([])), 0)

            # Add email address to party
            self.party.write([self.party], {
                'contact_mechanisms': [('create', [
                    {'type': 'email', 'value': 'party@ol.in'},
                ])],
            })
            payment_transaction.send_email_notification()

            # Check if no email was sent if there's no template
            self.assertEqual(len(self.EmailQueue.search([])), 0)


def suite():
    """
    Define suite
    """
    test_suite = trytond.tests.test_tryton.suite()
    test_suite.addTests([
        unittest.TestLoader().loadTestsFromTestCase(TestPaymentTransaction),
    ])
    return test_suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
