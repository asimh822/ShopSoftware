/**
 * OwnerBalancesScreen — suppliers, customers, bank accounts, cash in hand.
 * All data from Supabase — no Flask required.
 *
 * Cash formula matches db_cash_in_hand() in database.py exactly.
 * Bank formula matches db_bank_account_closing_balance() in database.py.
 * Supplier/customer formulas match _party_closing_balance() in database.py.
 *   Supplier : opening_balance + Σ purchase_vouchers + Σ payments(CR) - Σ payments(CP)
 *              + Σ journal_entries(debit) - Σ journal_entries(credit)
 *              - Σ journal_voucher_lines(debit) + Σ journal_voucher_lines(credit)
 *              (JVL is INVERTED vs journal_entries for suppliers — Debit reduces
 *              a liability, Credit increases it; the opposite of journal_entries'
 *              legacy debit/credit convention)
 *              - Σ sale_vouchers.total_amount where supplier_as_customer_id = this supplier
 *   Customer : opening_balance + Σ credit sale_vouchers + Σ payments(CP) - Σ payments(CR)
 *              + Σ journal_entries(debit) - Σ journal_entries(credit)
 *              + Σ journal_voucher_lines(debit) - Σ journal_voucher_lines(credit)
 *              - Σ purchase_vouchers.total_amount where customer_as_supplier_id = this customer
 *   Bank     : opening_balance + Σ sale_vouchers.bank_amount
 *              + Σ bank_transactions.CP - Σ bank_transactions.CR
 *              + Σ journal_voucher_lines(debit) - Σ journal_voucher_lines(credit)
 *              (no payments-table term — CP/CR to suppliers/customers is always cash;
 *              direct bank transfers go through journal_voucher_lines instead)
 *   Cash     : payments(CR) - payments(CP), regardless of payment_method, plus
 *              journal_voucher_lines(party_type='cash')
 */

import React, {useState, useEffect, useCallback} from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import {fmtPKR} from '../utils/formatting';
import {SUPABASE_URL, SUPABASE_KEY} from '../supabaseConfig';

const COLORS = {
  bg: '#F5F5F5',
  card: '#FFFFFF',
  primary: '#004D40',
  sectionBg: '#004D40',
  sectionText: '#fff',
  name: '#212121',
  balance: '#212121',
  border: '#E0E0E0',
  cashBg: '#E0F2F1',
  cashText: '#004D40',
  emptyText: '#BDBDBD',
};

const SB_HEADERS = {
  apikey: SUPABASE_KEY,
  Authorization: `Bearer ${SUPABASE_KEY}`,
  'Content-Type': 'application/json',
};

function arr(x) {
  return Array.isArray(x) ? x : [];
}

async function sbGet(path) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {headers: SB_HEADERS});
  return res.json();
}

function sumPayments(payments, partyType, partyId, vType) {
  return arr(payments)
    .filter(p => p.party_type === partyType && p.party_id === partyId && p.type === vType)
    .reduce((s, p) => s + (p.amount || 0), 0);
}

export default function OwnerBalancesScreen() {
  const [balances, setBalances] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const loadData = useCallback(async () => {
    setError('');
    try {
      const [
        suppliers,
        customers,
        bankAccounts,
        purchaseVouchers,
        saleVouchers,
        payments,
        bankTransactions,
        cashJournalLines,
        expensesRows,
        settingsRows,
        journalEntries,
        journalVoucherLines,
      ] = await Promise.all([
        sbGet('suppliers?select=id,name,opening_balance&id=neq.0&limit=1000'),
        sbGet('customers?select=id,name,opening_balance&type=eq.credit&limit=1000'),
        sbGet('bank_accounts?select=id,name,opening_balance&limit=200'),
        sbGet('purchase_vouchers?select=supplier_id,total_amount,purchase_type,cash_amount,customer_as_supplier_id&limit=10000'),
        sbGet('sale_vouchers?select=customer_id,total_amount,bank_account_id,bank_amount,cash_paid,supplier_as_customer_id&limit=10000'),
        sbGet('payments?select=party_type,party_id,amount,type&limit=10000'),
        sbGet('bank_transactions?select=type,source,bank_account_id,amount&limit=10000'),
        sbGet('cash_journal_lines?select=direction,amount&limit=10000'),
        sbGet('expenses?select=payment_method,amount&limit=10000'),
        sbGet('settings?select=key,value&key=eq.cash_opening_balance'),
        sbGet('journal_entries?select=party_type,party_id,amount,type&limit=10000'),
        sbGet('journal_voucher_lines?select=party_type,party_id,debit,credit&limit=10000'),
      ]);

      // Aggregates for supplier/customer balances
      const pvBySupplier = {};
      arr(purchaseVouchers).forEach(pv => {
        if (pv.supplier_id != null) {
          pvBySupplier[pv.supplier_id] = (pvBySupplier[pv.supplier_id] || 0) + (pv.total_amount || 0);
        }
      });

      const svByCustomer = {};
      arr(saleVouchers).forEach(sv => {
        if (sv.customer_id != null) {
          svByCustomer[sv.customer_id] = (svByCustomer[sv.customer_id] || 0) + (sv.total_amount || 0);
        }
      });

      const svBySupplierAsCustomer = {};
      arr(saleVouchers).forEach(sv => {
        if (sv.supplier_as_customer_id != null) {
          svBySupplierAsCustomer[sv.supplier_as_customer_id] =
            (svBySupplierAsCustomer[sv.supplier_as_customer_id] || 0) + (sv.total_amount || 0);
        }
      });

      const pvByCustomerAsSupplier = {};
      arr(purchaseVouchers).forEach(pv => {
        if (pv.customer_as_supplier_id != null) {
          pvByCustomerAsSupplier[pv.customer_as_supplier_id] =
            (pvByCustomerAsSupplier[pv.customer_as_supplier_id] || 0) + (pv.total_amount || 0);
        }
      });

      // Supplier balances
      const supplierBalances = arr(suppliers)
        .map(s => {
          const ob = s.opening_balance || 0;
          const pv = pvBySupplier[s.id] || 0;
          const cp = sumPayments(payments, 'supplier', s.id, 'CP');
          const cr = sumPayments(payments, 'supplier', s.id, 'CR');
          const sac = svBySupplierAsCustomer[s.id] || 0;
          const jeDebit = arr(journalEntries)
            .filter(je => je.party_type === 'supplier' && je.party_id === s.id && je.type === 'debit')
            .reduce((sum, je) => sum + (je.amount || 0), 0);
          const jeCredit = arr(journalEntries)
            .filter(je => je.party_type === 'supplier' && je.party_id === s.id && je.type === 'credit')
            .reduce((sum, je) => sum + (je.amount || 0), 0);
          const jvlDebit = arr(journalVoucherLines)
            .filter(jvl => jvl.party_type === 'supplier' && jvl.party_id === s.id)
            .reduce((sum, jvl) => sum + (jvl.debit || 0), 0);
          const jvlCredit = arr(journalVoucherLines)
            .filter(jvl => jvl.party_type === 'supplier' && jvl.party_id === s.id)
            .reduce((sum, jvl) => sum + (jvl.credit || 0), 0);
          // NOTE: journal_voucher_lines Dr/Cr is the opposite direction from
          // jeDebit/jeCredit above for a supplier (liability) — Debit reduces
          // the balance, Credit increases it. Matches _party_closing_balance()
          // in database.py exactly.
          const balance = Math.round(
            (ob + pv + cr - cp + jeDebit - jeCredit - jvlDebit + jvlCredit - sac) * 100,
          ) / 100;
          return {id: s.id, name: s.name, balance};
        })
        .filter(s => Math.abs(s.balance) >= 0.01);

      // Customer balances
      const customerBalances = arr(customers)
        .map(c => {
          const ob = c.opening_balance || 0;
          const sv = svByCustomer[c.id] || 0;
          const cr = sumPayments(payments, 'customer', c.id, 'CR');
          const cp = sumPayments(payments, 'customer', c.id, 'CP');
          const cas = pvByCustomerAsSupplier[c.id] || 0;
          const jeDebit = arr(journalEntries)
            .filter(je => je.party_type === 'customer' && je.party_id === c.id && je.type === 'debit')
            .reduce((sum, je) => sum + (je.amount || 0), 0);
          const jeCredit = arr(journalEntries)
            .filter(je => je.party_type === 'customer' && je.party_id === c.id && je.type === 'credit')
            .reduce((sum, je) => sum + (je.amount || 0), 0);
          const jvlDebit = arr(journalVoucherLines)
            .filter(jvl => jvl.party_type === 'customer' && jvl.party_id === c.id)
            .reduce((sum, jvl) => sum + (jvl.debit || 0), 0);
          const jvlCredit = arr(journalVoucherLines)
            .filter(jvl => jvl.party_type === 'customer' && jvl.party_id === c.id)
            .reduce((sum, jvl) => sum + (jvl.credit || 0), 0);
          const balance = Math.round(
            (ob + sv + cp - cr + jeDebit - jeCredit + jvlDebit - jvlCredit - cas) * 100,
          ) / 100;
          return {id: c.id, name: c.name, balance};
        })
        .filter(c => Math.abs(c.balance) >= 0.01);

      // Bank account balances — matches db_bank_account_closing_balance()
      // btCR includes cash withdrawals (source='cash_transfer'),
      //         expense payments (source='expense'), JV credits (source='jv')
      const bankSales = {};
      arr(saleVouchers).forEach(sv => {
        if (sv.bank_account_id != null && (sv.bank_amount || 0) > 0) {
          bankSales[sv.bank_account_id] = (bankSales[sv.bank_account_id] || 0) + (sv.bank_amount || 0);
        }
      });
      const bankAccountBalances = arr(bankAccounts).map(ba => {
        const ob = ba.opening_balance || 0;
        const sales = bankSales[ba.id] || 0;
        const btCP = arr(bankTransactions)
          .filter(bt => bt.bank_account_id === ba.id && bt.type === 'CP')
          .reduce((s, bt) => s + (bt.amount || 0), 0);
        const btCR = arr(bankTransactions)
          .filter(bt => bt.bank_account_id === ba.id && bt.type === 'CR')
          .reduce((s, bt) => s + (bt.amount || 0), 0);
        const jvlDr = arr(journalVoucherLines)
          .filter(jvl => jvl.party_type === 'bank' && jvl.party_id === ba.id)
          .reduce((s, jvl) => s + (jvl.debit || 0), 0);
        const jvlCr = arr(journalVoucherLines)
          .filter(jvl => jvl.party_type === 'bank' && jvl.party_id === ba.id)
          .reduce((s, jvl) => s + (jvl.credit || 0), 0);
        const balance = Math.round(
          (ob + sales + btCP - btCR + jvlDr - jvlCr) * 100,
        ) / 100;
        return {id: ba.id, name: ba.name, balance};
      });

      // Cash in hand — matches db_cash_in_hand() in database.py
      const settingsMap = {};
      arr(settingsRows).forEach(r => { settingsMap[r.key] = r.value; });
      const cashOB = parseFloat(settingsMap.cash_opening_balance || '0') || 0;

      const cashFromSales = arr(saleVouchers)
        .reduce((s, sv) => s + (sv.cash_paid || 0), 0);
      const cashPayIn = arr(payments)
        .filter(p => p.type === 'CR')
        .reduce((s, p) => s + (p.amount || 0), 0);
      const cashPayOut = arr(payments)
        .filter(p => p.type === 'CP')
        .reduce((s, p) => s + (p.amount || 0), 0);
      const btCashIn = arr(bankTransactions)
        .filter(bt => bt.type === 'CR' && bt.source === 'cash_transfer')
        .reduce((s, bt) => s + (bt.amount || 0), 0);
      const btCashOut = arr(bankTransactions)
        .filter(bt => bt.type === 'CP' && bt.source === 'cash_transfer')
        .reduce((s, bt) => s + (bt.amount || 0), 0);
      const cjlIn = arr(cashJournalLines)
        .filter(cjl => cjl.direction === 'in')
        .reduce((s, cjl) => s + (cjl.amount || 0), 0);
      const cjlOut = arr(cashJournalLines)
        .filter(cjl => cjl.direction === 'out')
        .reduce((s, cjl) => s + (cjl.amount || 0), 0);
      const cashPurchases = arr(purchaseVouchers)
        .filter(pv => pv.purchase_type === 'cash')
        .reduce((s, pv) => s + (pv.cash_amount || 0), 0);
      const cashExpenses = arr(expensesRows)
        .filter(e => e.payment_method === 'cash')
        .reduce((s, e) => s + (e.amount || 0), 0);
      const jvlCashDr = arr(journalVoucherLines)
        .filter(jvl => jvl.party_type === 'cash')
        .reduce((s, jvl) => s + (jvl.debit || 0), 0);
      const jvlCashCr = arr(journalVoucherLines)
        .filter(jvl => jvl.party_type === 'cash')
        .reduce((s, jvl) => s + (jvl.credit || 0), 0);

      const cashInHand =
        cashOB + cashFromSales + cashPayIn - cashPayOut
        + btCashIn - btCashOut
        + cjlIn - cjlOut
        - cashPurchases - cashExpenses
        + jvlCashDr - jvlCashCr;

      setBalances({
        suppliers: supplierBalances,
        customers: customerBalances,
        bank_accounts: bankAccountBalances,
        cash_in_hand: cashInHand,
      });
    } catch (_err) {
      setError('Failed to load');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const onRefresh = () => { setRefreshing(true); loadData(); };

  const buildListData = () => {
    if (!balances) return [];
    const items = [];

    items.push({type: 'header', title: 'Suppliers (We Owe)'});
    if (balances.suppliers?.length) {
      balances.suppliers.forEach(s =>
        items.push({type: 'row', ...s, rowKey: `sup-${s.id}`}),
      );
    } else {
      items.push({type: 'empty', rowKey: 'sup-empty'});
    }

    items.push({type: 'header', title: 'Customers (They Owe)'});
    if (balances.customers?.length) {
      balances.customers.forEach(c =>
        items.push({type: 'row', ...c, rowKey: `cust-${c.id}`}),
      );
    } else {
      items.push({type: 'empty', rowKey: 'cust-empty'});
    }

    items.push({type: 'header', title: 'Bank Accounts'});
    if (balances.bank_accounts?.length) {
      balances.bank_accounts.forEach(b =>
        items.push({type: 'row', ...b, rowKey: `bank-${b.id}`}),
      );
    } else {
      items.push({type: 'empty', rowKey: 'bank-empty'});
    }

    items.push({type: 'header', title: 'Cash in Hand'});
    items.push({type: 'cash', amount: balances.cash_in_hand ?? 0, rowKey: 'cash'});

    return items;
  };

  const renderItem = ({item}) => {
    if (item.type === 'header') {
      return (
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>{item.title}</Text>
        </View>
      );
    }
    if (item.type === 'empty') {
      return (
        <View style={styles.emptyRow}>
          <Text style={styles.emptyText}>All settled</Text>
        </View>
      );
    }
    if (item.type === 'cash') {
      return (
        <View style={styles.cashCard}>
          <Text style={styles.cashLabel}>Cash in Hand</Text>
          <Text style={styles.cashAmount}>Rs. {fmtPKR(item.amount)}</Text>
        </View>
      );
    }
    return (
      <View style={styles.row}>
        <Text style={styles.rowName}>{item.name}</Text>
        <Text style={styles.rowBalance}>Rs. {fmtPKR(item.balance)}</Text>
      </View>
    );
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>{error}</Text>
      </View>
    );
  }

  return (
    <FlatList
      style={styles.container}
      data={buildListData()}
      keyExtractor={(item, idx) => item.rowKey || `${item.type}-${item.title || idx}`}
      renderItem={renderItem}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={onRefresh}
          colors={[COLORS.primary]}
        />
      }
    />
  );
}

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: COLORS.bg},
  center: {flex: 1, justifyContent: 'center', alignItems: 'center'},
  errorText: {fontSize: 15, color: '#B71C1C'},
  sectionHeader: {
    backgroundColor: COLORS.sectionBg,
    paddingHorizontal: 16,
    paddingVertical: 10,
    marginTop: 12,
  },
  sectionTitle: {
    color: COLORS.sectionText,
    fontWeight: 'bold',
    fontSize: 13,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  row: {
    backgroundColor: COLORS.card,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  rowName: {flex: 1, fontSize: 14, color: COLORS.name, fontWeight: '500'},
  rowBalance: {fontSize: 15, fontWeight: 'bold', color: COLORS.balance},
  emptyRow: {
    backgroundColor: COLORS.card,
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  emptyText: {fontSize: 13, color: COLORS.emptyText, fontStyle: 'italic'},
  cashCard: {
    backgroundColor: COLORS.cashBg,
    marginHorizontal: 12,
    marginTop: 8,
    marginBottom: 16,
    borderRadius: 10,
    paddingHorizontal: 20,
    paddingVertical: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    elevation: 2,
    shadowColor: '#000',
    shadowOpacity: 0.06,
    shadowRadius: 3,
    shadowOffset: {width: 0, height: 1},
  },
  cashLabel: {fontSize: 14, color: COLORS.cashText, fontWeight: '600'},
  cashAmount: {fontSize: 20, fontWeight: 'bold', color: COLORS.cashText},
});
