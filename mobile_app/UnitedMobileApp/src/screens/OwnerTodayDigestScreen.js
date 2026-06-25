/**
 * OwnerTodayDigestScreen — daily digest matching build_daily_digest() output.
 * Shows today's key metrics: sales count/total, gross profit, net cash change,
 * net bank change, credit given/collected, cash expenses, below-cost items,
 * biggest discount. All data from Supabase — no Flask required.
 *
 * Cash/bank formulas mirror db_cash_book() and build_daily_digest() exactly.
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
import {fmtPKR, todayDDMMYYYY} from '../utils/formatting';
import {SUPABASE_URL, SUPABASE_KEY} from '../supabaseConfig';

const COLORS = {
  bg: '#F5F5F5',
  card: '#FFFFFF',
  primary: '#1565C0',
  profit: '#1B5E20',
  profitBg: '#E8F5E9',
  profitBorder: '#A5D6A7',
  warn: '#B71C1C',
  warnBg: '#FFEBEE',
  warnBorder: '#EF9A9A',
  label: '#757575',
  value: '#212121',
  subtext: '#9E9E9E',
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
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    headers: SB_HEADERS,
  });
  return res.json();
}

function MetricCard({label, value, style, labelStyle, valueStyle}) {
  return (
    <View style={[styles.card, style]}>
      <Text style={[styles.cardLabel, labelStyle]}>{label}</Text>
      <Text style={[styles.cardValue, valueStyle]}>{value}</Text>
    </View>
  );
}

export default function OwnerTodayDigestScreen() {
  const [data, setData] = useState(null);
  const [todayLabel, setTodayLabel] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const loadData = useCallback(async () => {
    setError('');
    try {
      const today = todayDDMMYYYY();
      setTodayLabel(today);
      const enc = encodeURIComponent(today);

      // Parallel: all today-scoped tables
      const [svRows, payRows, btRows, pvRows, expRows, cjlRows] =
        await Promise.all([
          sbGet(
            `sale_vouchers?date=eq.${enc}&select=id,total_amount,type,cash_paid,bank_amount,discount`,
          ),
          sbGet(`payments?date=eq.${enc}&select=amount,type,party_type`),
          sbGet(`bank_transactions?date=eq.${enc}&select=amount,type,source`),
          sbGet(
            `purchase_vouchers?date=eq.${enc}&select=purchase_type,cash_amount`,
          ),
          sbGet(`expenses?date=eq.${enc}&select=amount,payment_method`),
          sbGet(`cash_journal_lines?date=eq.${enc}&select=amount,direction`),
        ]);

      // Gross profit + below-cost — needs sale_lines → stock_items
      let grossProfit = 0;
      let belowCostCount = 0;
      const svIds = arr(svRows)
        .map(r => r.id)
        .filter(Boolean);
      if (svIds.length > 0) {
        const slRows = await sbGet(
          `sale_lines?sv_id=in.(${svIds.join(',')})&select=final_price,stock_item_id`,
        );
        const siIds = [
          ...new Set(arr(slRows).map(r => r.stock_item_id).filter(Boolean)),
        ];
        if (siIds.length > 0) {
          const siRows = await sbGet(
            `stock_items?id=in.(${siIds.join(',')})&select=id,purchase_price`,
          );
          const siMap = {};
          arr(siRows).forEach(si => {
            siMap[si.id] = si.purchase_price || 0;
          });
          arr(slRows).forEach(sl => {
            const pp = siMap[sl.stock_item_id] || 0;
            const fp = sl.final_price || 0;
            grossProfit += fp - pp;
            if (fp < pp) {
              belowCostCount++;
            }
          });
        }
      }

      // ── Sales metrics ──────────────────────────────────────────────────────
      const salesCount = arr(svRows).length;
      const salesTotal = arr(svRows).reduce(
        (s, r) => s + (r.total_amount || 0),
        0,
      );
      const creditGiven = arr(svRows)
        .filter(r => r.type === 'credit')
        .reduce((s, r) => s + (r.total_amount || 0), 0);
      const biggestDiscount = arr(svRows).reduce(
        (m, r) => Math.max(m, r.discount || 0),
        0,
      );

      // ── Credit collected ───────────────────────────────────────────────────
      const creditCollected = arr(payRows)
        .filter(p => p.type === 'CR' && p.party_type === 'customer')
        .reduce((s, p) => s + (p.amount || 0), 0);

      // ── Cash expenses ──────────────────────────────────────────────────────
      const expensesCash = arr(expRows)
        .filter(e => (e.payment_method || '').toLowerCase() === 'cash')
        .reduce((s, e) => s + (e.amount || 0), 0);

      // ── Net cash today — mirrors db_cash_book() ────────────────────────────
      // Cash IN:  sales cash_paid + CR payments + bank withdrawal (btCashIn) + JV in
      // Cash OUT: CP payments + bank deposit (btCashOut) + cash purchases + expenses + JV out
      const cashFromSales = arr(svRows).reduce(
        (s, r) => s + (r.cash_paid || 0),
        0,
      );
      const cashPayIn = arr(payRows)
        .filter(p => p.type === 'CR')
        .reduce((s, p) => s + (p.amount || 0), 0);
      const cashPayOut = arr(payRows)
        .filter(p => p.type === 'CP')
        .reduce((s, p) => s + (p.amount || 0), 0);
      const btCashIn = arr(btRows)
        .filter(bt => bt.type === 'CR' && bt.source === 'cash_transfer')
        .reduce((s, bt) => s + (bt.amount || 0), 0);
      const btCashOut = arr(btRows)
        .filter(bt => bt.type === 'CP' && bt.source === 'cash_transfer')
        .reduce((s, bt) => s + (bt.amount || 0), 0);
      const cjlIn = arr(cjlRows)
        .filter(cjl => cjl.direction === 'in')
        .reduce((s, cjl) => s + (cjl.amount || 0), 0);
      const cjlOut = arr(cjlRows)
        .filter(cjl => cjl.direction === 'out')
        .reduce((s, cjl) => s + (cjl.amount || 0), 0);
      const cashPurch = arr(pvRows)
        .filter(pv => pv.purchase_type === 'cash')
        .reduce((s, pv) => s + (pv.cash_amount || 0), 0);

      const netCash =
        cashFromSales +
        cashPayIn +
        btCashIn +
        cjlIn -
        cashPayOut -
        btCashOut -
        cashPurch -
        expensesCash -
        cjlOut;

      // ── Net bank today ─────────────────────────────────────────────────────
      // Bank IN:  bank sales + bank deposits (btCP)
      // Bank OUT: bank withdrawals (btCR)
      const bankFromSales = arr(svRows).reduce(
        (s, r) => s + (r.bank_amount || 0),
        0,
      );
      const bankIn = arr(btRows)
        .filter(bt => bt.type === 'CP')
        .reduce((s, bt) => s + (bt.amount || 0), 0);
      const bankOut = arr(btRows)
        .filter(bt => bt.type === 'CR')
        .reduce((s, bt) => s + (bt.amount || 0), 0);
      const netBank = bankFromSales + bankIn - bankOut;

      const round2 = v => Math.round(v * 100) / 100;
      setData({
        salesCount,
        salesTotal: round2(salesTotal),
        grossProfit: round2(grossProfit),
        netCash: round2(netCash),
        netBank: round2(netBank),
        creditGiven: round2(creditGiven),
        creditCollected: round2(creditCollected),
        expensesCash: round2(expensesCash),
        belowCostCount,
        biggestDiscount: round2(biggestDiscount),
      });
    } catch (_err) {
      setError('Failed to load data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const onRefresh = () => {
    setRefreshing(true);
    loadData();
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

  const d = data || {};
  const profitPositive = (d.grossProfit || 0) >= 0;
  const hasBelow = (d.belowCostCount || 0) > 0;

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
      <Text style={styles.dateLabel}>{todayLabel}</Text>

      {/* Sales row */}
      <View style={styles.row}>
        <MetricCard
          label="SALES"
          value={`${d.salesCount || 0} vouchers`}
          style={styles.halfCard}
        />
        <MetricCard
          label="TOTAL AMOUNT"
          value={`Rs. ${fmtPKR(d.salesTotal)}`}
          style={styles.halfCard}
        />
      </View>

      {/* Gross profit — full width, coloured */}
      <MetricCard
        label="GROSS PROFIT"
        value={`Rs. ${fmtPKR(d.grossProfit)}`}
        style={{
          backgroundColor: profitPositive ? COLORS.profitBg : COLORS.warnBg,
          borderWidth: 1,
          borderColor: profitPositive ? COLORS.profitBorder : COLORS.warnBorder,
        }}
        labelStyle={{
          color: profitPositive ? COLORS.profit : COLORS.warn,
        }}
        valueStyle={{
          fontSize: 22,
          color: profitPositive ? COLORS.profit : COLORS.warn,
        }}
      />

      {/* Net cash + bank row */}
      <View style={styles.row}>
        <MetricCard
          label="NET CASH TODAY"
          value={`Rs. ${fmtPKR(d.netCash)}`}
          style={styles.halfCard}
        />
        <MetricCard
          label="NET BANK TODAY"
          value={`Rs. ${fmtPKR(d.netBank)}`}
          style={styles.halfCard}
        />
      </View>

      {/* Credit row */}
      <View style={styles.row}>
        <MetricCard
          label="CREDIT GIVEN"
          value={`Rs. ${fmtPKR(d.creditGiven)}`}
          style={styles.halfCard}
        />
        <MetricCard
          label="CREDIT COLLECTED"
          value={`Rs. ${fmtPKR(d.creditCollected)}`}
          style={styles.halfCard}
        />
      </View>

      {/* Cash expenses (only when non-zero) */}
      {(d.expensesCash || 0) > 0 && (
        <MetricCard
          label="CASH EXPENSES"
          value={`Rs. ${fmtPKR(d.expensesCash)}`}
        />
      )}

      {/* Below cost + biggest discount */}
      <View style={styles.row}>
        <MetricCard
          label="BELOW COST"
          value={hasBelow ? `${d.belowCostCount} item(s)` : 'None'}
          style={[
            styles.halfCard,
            hasBelow && {
              backgroundColor: COLORS.warnBg,
              borderWidth: 1,
              borderColor: COLORS.warnBorder,
            },
          ]}
          labelStyle={hasBelow ? {color: COLORS.warn} : {}}
          valueStyle={hasBelow ? {color: COLORS.warn} : {}}
        />
        <MetricCard
          label="BIGGEST DISCOUNT"
          value={
            (d.biggestDiscount || 0) > 0
              ? `Rs. ${fmtPKR(d.biggestDiscount)}`
              : 'None'
          }
          style={styles.halfCard}
        />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: COLORS.bg},
  content: {padding: 16, paddingBottom: 32},
  center: {flex: 1, justifyContent: 'center', alignItems: 'center'},
  errorText: {fontSize: 15, color: COLORS.warn},
  dateLabel: {
    fontSize: 12,
    color: COLORS.subtext,
    fontWeight: '600',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    marginBottom: 16,
  },
  row: {
    flexDirection: 'row',
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
    fontSize: 11,
    color: COLORS.label,
    fontWeight: '600',
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  cardValue: {
    fontSize: 17,
    fontWeight: 'bold',
    color: COLORS.value,
  },
});
