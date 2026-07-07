/**
 * OwnerDashboardScreen — 5-card summary: today's sales, purchases, profit,
 * cash in hand, bank balance. All data from Supabase — no Flask required.
 *
 * Cash formula matches db_cash_in_hand() in database.py exactly.
 * Bank formula matches db_bank_account_closing_balance() in database.py.
 */

import React, {useState, useEffect, useCallback} from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import {fmtPKR} from '../utils/formatting';
import {SUPABASE_URL, SUPABASE_KEY} from '../supabaseConfig';

const COLORS = {
  bg: '#F5F5F5',
  card: '#FFFFFF',
  primary: '#263238',
  profit: '#1B5E20',
  profitBg: '#E8F5E9',
  label: '#757575',
  value: '#212121',
};

const SB_HEADERS = {
  apikey: SUPABASE_KEY,
  Authorization: `Bearer ${SUPABASE_KEY}`,
  'Content-Type': 'application/json',
};

function getTodayDDMMYYYY() {
  const d = new Date();
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return `${dd}/${mm}/${d.getFullYear()}`;
}

function arr(x) {
  return Array.isArray(x) ? x : [];
}

async function sbGet(path) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {headers: SB_HEADERS});
  return res.json();
}

function AmountCard({label, amount, style, labelStyle, valueStyle}) {
  return (
    <View style={[styles.card, style]}>
      <Text style={[styles.cardLabel, labelStyle]}>{label}</Text>
      <Text style={[styles.cardValue, valueStyle]}>Rs. {fmtPKR(amount)}</Text>
    </View>
  );
}

export default function OwnerDashboardScreen() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const loadData = useCallback(async () => {
    setError('');
    try {
      const today = getTodayDDMMYYYY();
      const todayEnc = encodeURIComponent(today);

      // Parallel fetch: today's totals + all-time data for cash/bank
      const [
        svTodayRows,
        pvTodayRows,
        allSaleVouchers,
        allPurchaseVouchers,
        payments,
        bankTransactions,
        cashJournalLines,
        journalVoucherLines,
        bankAccounts,
        expensesRows,
        settingsRows,
      ] = await Promise.all([
        sbGet(`sale_vouchers?date=eq.${todayEnc}&select=id,total_amount`),
        sbGet(`purchase_vouchers?date=eq.${todayEnc}&select=total_amount`),
        sbGet('sale_vouchers?select=cash_paid,bank_account_id,bank_amount&limit=10000'),
        sbGet('purchase_vouchers?select=purchase_type,cash_amount&limit=10000'),
        sbGet('payments?select=amount,type&limit=10000'),
        sbGet('bank_transactions?select=type,source,bank_account_id,amount&limit=10000'),
        sbGet('cash_journal_lines?select=direction,amount&limit=10000'),
        sbGet('journal_voucher_lines?select=party_type,party_id,debit,credit&limit=10000'),
        sbGet('bank_accounts?select=id,opening_balance&limit=100'),
        sbGet('expenses?select=payment_method,amount&limit=10000'),
        sbGet('settings?select=key,value&key=eq.cash_opening_balance'),
      ]);

      // Today's totals
      const todaySalesTotal = arr(svTodayRows).reduce((s, r) => s + (r.total_amount || 0), 0);
      const todayPurchasesTotal = arr(pvTodayRows).reduce((s, r) => s + (r.total_amount || 0), 0);

      // Today's profit: sale_lines → stock_items
      let todayProfit = 0;
      const svIds = arr(svTodayRows).map(r => r.id).filter(Boolean);
      if (svIds.length > 0) {
        const slRows = await sbGet(
          `sale_lines?sv_id=in.(${svIds.join(',')})&select=final_price,stock_item_id`,
        );
        const siIds = [...new Set(arr(slRows).map(r => r.stock_item_id).filter(Boolean))];
        if (siIds.length > 0) {
          const siRows = await sbGet(
            `stock_items?id=in.(${siIds.join(',')})&select=id,purchase_price`,
          );
          const siMap = {};
          arr(siRows).forEach(si => { siMap[si.id] = si.purchase_price || 0; });
          todayProfit = arr(slRows).reduce(
            (s, sl) => s + (sl.final_price || 0) - (siMap[sl.stock_item_id] || 0),
            0,
          );
        }
      }

      // ── Cash in hand — matches db_cash_in_hand() in database.py ─────────────
      const settingsMap = {};
      arr(settingsRows).forEach(r => { settingsMap[r.key] = r.value; });
      const cashOB = parseFloat(settingsMap.cash_opening_balance || '0') || 0;

      const cashFromSales = arr(allSaleVouchers)
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
      const cashPurchases = arr(allPurchaseVouchers)
        .filter(pv => pv.purchase_type === 'cash')
        .reduce((s, pv) => s + (pv.cash_amount || 0), 0);
      const cashExpenses = arr(expensesRows)
        .filter(e => e.payment_method === 'cash')
        .reduce((s, e) => s + (e.amount || 0), 0);
      // JV redesign — Dr Cash / Cr Cash lines in journal_voucher_lines
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

      // ── Bank total — matches db_bank_account_closing_balance() in database.py ──
      // opening_balance
      // + bank sales (sale_vouchers.bank_amount)
      // + bank_transactions type='CP' (cash deposits into bank, JV debits)
      // - bank_transactions type='CR' (cash withdrawals, expenses, JV credits)
      // + journal_voucher_lines debit/credit where party_type='bank' (JV redesign —
      //   e.g. "Bank transfer to supplier -> Dr Supplier / Cr Bank")
      // NOTE: the payments table has no bank_account_id/payment_method term in
      // the desktop formula at all — CP/CR to suppliers/customers are always
      // cash; direct bank transfers go through journal_voucher_lines instead.

      const bankSalesByAcct = {};
      arr(allSaleVouchers).forEach(sv => {
        if (sv.bank_account_id && (sv.bank_amount || 0) > 0) {
          bankSalesByAcct[sv.bank_account_id] =
            (bankSalesByAcct[sv.bank_account_id] || 0) + (sv.bank_amount || 0);
        }
      });

      const bankTotal = arr(bankAccounts).reduce((total, ba) => {
        const ob = ba.opening_balance || 0;
        const sales = bankSalesByAcct[ba.id] || 0;
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
        return total + ob + sales + btCP - btCR + jvlDr - jvlCr;
      }, 0);

      setData({
        today_sales_total: todaySalesTotal,
        today_purchases_total: todayPurchasesTotal,
        today_profit: todayProfit,
        cash_in_hand: cashInHand,
        bank_total: bankTotal,
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
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={onRefresh}
          colors={[COLORS.primary]}
        />
      }>
      <View style={styles.grid}>
        <AmountCard
          label="Today's Sales"
          amount={data?.today_sales_total ?? 0}
          style={styles.halfCard}
        />
        <AmountCard
          label="Today's Purchases"
          amount={data?.today_purchases_total ?? 0}
          style={styles.halfCard}
        />
        <AmountCard
          label="Cash in Hand"
          amount={data?.cash_in_hand ?? 0}
          style={styles.halfCard}
        />
        <AmountCard
          label="Bank Balance"
          amount={data?.bank_total ?? 0}
          style={styles.halfCard}
        />
      </View>

      <AmountCard
        label="Today's Profit"
        amount={data?.today_profit ?? 0}
        style={styles.profitCard}
        labelStyle={styles.profitLabel}
        valueStyle={styles.profitValue}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: COLORS.bg},
  content: {padding: 16},
  center: {flex: 1, justifyContent: 'center', alignItems: 'center'},
  errorText: {fontSize: 15, color: '#B71C1C'},
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginHorizontal: -6,
  },
  card: {
    backgroundColor: COLORS.card,
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    elevation: 2,
    shadowColor: '#000',
    shadowOpacity: 0.08,
    shadowRadius: 4,
    shadowOffset: {width: 0, height: 2},
  },
  halfCard: {
    flex: 1,
    marginHorizontal: 6,
    minWidth: '40%',
  },
  cardLabel: {
    fontSize: 12,
    color: COLORS.label,
    fontWeight: '500',
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 0.3,
  },
  cardValue: {
    fontSize: 17,
    fontWeight: 'bold',
    color: COLORS.value,
  },
  profitCard: {
    backgroundColor: COLORS.profitBg,
    borderWidth: 1,
    borderColor: '#A5D6A7',
  },
  profitLabel: {color: COLORS.profit},
  profitValue: {fontSize: 22, color: COLORS.profit},
});
