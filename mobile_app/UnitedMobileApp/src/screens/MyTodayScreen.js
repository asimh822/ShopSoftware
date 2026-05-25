/**
 * MyTodayScreen — salesman's daily summary.
 * Shows summary cards + list of today's sales.
 * Pull-to-refresh.
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
import {apiGet, getSalesmanId, getSalesmanName} from '../config/api';
import {fmtPKR, todayDDMMYYYY} from '../utils/formatting';

const COLORS = {
  primary: '#6A1B9A',
  bg: '#F5F5F5',
  card: '#FFFFFF',
  border: '#E0E0E0',
  text: '#212121',
  subtext: '#757575',
};

export default function MyTodayScreen({navigation}) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [summary, setSummary] = useState({units: 0, total: 0});
  const [sales, setSales] = useState([]);
  const [salesmanName, setSalesmanName] = useState('');

  const today = todayDDMMYYYY();

  useEffect(() => {
    initLoad();
  }, []);

  const initLoad = async () => {
    const name = await getSalesmanName();
    setSalesmanName(name || '');
    await loadData();
  };

  const loadData = useCallback(async () => {
    const salesman_id = await getSalesmanId();
    try {
      const data = await apiGet('/api/salesman/today', {salesman_id});
      if (data.success) {
        setSummary({
          units: data.units_sold,
          total: data.total_amount,
        });
        setSales(data.sales || []);
      }
    } catch (err) {
      if (err.message === 'SESSION_EXPIRED') navigation.replace('Login');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const onRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const renderSale = ({item}) => (
    <View style={styles.saleCard}>
      <View style={styles.saleHeader}>
        <Text style={styles.svNumber}>{item.sv_number}</Text>
        <Text
          style={[
            styles.saleType,
            item.type === 'cash' ? styles.typeCash : styles.typeCredit,
          ]}>
          {item.type.toUpperCase()}
        </Text>
      </View>
      <Text style={styles.customerName}>
        {item.customer_name || item.cash_customer_name || '—'}
      </Text>
      <View style={styles.saleFooter}>
        <Text style={styles.itemsCount}>{item.items} phone{item.items !== 1 ? 's' : ''}</Text>
        <Text style={styles.saleTotal}>PKR {fmtPKR(item.total_amount)}</Text>
      </View>
    </View>
  );

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  return (
    <FlatList
      style={styles.container}
      contentContainerStyle={styles.content}
      data={sales}
      keyExtractor={item => String(item.id)}
      renderItem={renderSale}
      ListHeaderComponent={
        <>
          {/* Date + name banner */}
          <View style={styles.banner}>
            <Text style={styles.bannerDate}>{today}</Text>
            <Text style={styles.bannerName}>{salesmanName}</Text>
          </View>

          {/* Summary cards */}
          <View style={styles.cardsRow}>
            <View style={[styles.summaryCard, styles.cardUnits]}>
              <Text style={styles.cardValue}>{summary.units}</Text>
              <Text style={styles.cardLabel}>Phones Sold</Text>
            </View>
            <View style={[styles.summaryCard, styles.cardTotal]}>
              <Text style={styles.cardValue}>PKR</Text>
              <Text style={styles.cardAmount}>{fmtPKR(summary.total)}</Text>
              <Text style={styles.cardLabel}>Total Sales</Text>
            </View>
          </View>

          {sales.length > 0 && (
            <Text style={styles.sectionHeader}>Today's Invoices</Text>
          )}
        </>
      }
      ListEmptyComponent={
        <View style={styles.empty}>
          <Text style={styles.emptyIcon}>📋</Text>
          <Text style={styles.emptyText}>No sales recorded today.</Text>
          <Text style={styles.emptyHint}>
            Tap "New Sale" from the home screen to get started.
          </Text>
        </View>
      }
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
  content: {padding: 16},
  center: {flex: 1, justifyContent: 'center', alignItems: 'center'},
  banner: {
    backgroundColor: COLORS.primary,
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    alignItems: 'center',
  },
  bannerDate: {color: 'rgba(255,255,255,0.7)', fontSize: 13},
  bannerName: {color: '#fff', fontSize: 20, fontWeight: 'bold', marginTop: 4},
  cardsRow: {
    flexDirection: 'row',
    marginBottom: 16,
  },
  summaryCard: {
    flex: 1,
    borderRadius: 10,
    padding: 16,
    alignItems: 'center',
    elevation: 2,
    shadowColor: '#000',
    shadowOpacity: 0.08,
    shadowRadius: 4,
    shadowOffset: {width: 0, height: 2},
  },
  cardUnits: {
    backgroundColor: '#EDE7F6',
    marginRight: 6,
  },
  cardTotal: {
    backgroundColor: '#E8F5E9',
    marginLeft: 6,
  },
  cardValue: {
    fontSize: 28,
    fontWeight: 'bold',
    color: COLORS.primary,
  },
  cardAmount: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#2E7D32',
  },
  cardLabel: {
    fontSize: 12,
    color: COLORS.subtext,
    marginTop: 4,
    textAlign: 'center',
  },
  sectionHeader: {
    fontSize: 14,
    fontWeight: '700',
    color: COLORS.subtext,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 10,
  },
  saleCard: {
    backgroundColor: COLORS.card,
    borderRadius: 10,
    padding: 14,
    marginBottom: 10,
    elevation: 1,
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowRadius: 3,
    shadowOffset: {width: 0, height: 1},
  },
  saleHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  svNumber: {fontSize: 15, fontWeight: 'bold', color: COLORS.primary},
  saleType: {
    fontSize: 11,
    fontWeight: 'bold',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
  },
  typeCash: {backgroundColor: '#E3F2FD', color: '#1565C0'},
  typeCredit: {backgroundColor: '#E8F5E9', color: '#2E7D32'},
  customerName: {fontSize: 14, color: COLORS.text, marginBottom: 8},
  saleFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  itemsCount: {fontSize: 13, color: COLORS.subtext},
  saleTotal: {fontSize: 15, fontWeight: 'bold', color: COLORS.text},
  empty: {
    alignItems: 'center',
    paddingTop: 30,
    paddingHorizontal: 40,
  },
  emptyIcon: {fontSize: 48, marginBottom: 12},
  emptyText: {fontSize: 16, fontWeight: '600', color: COLORS.text, textAlign: 'center'},
  emptyHint: {
    fontSize: 13,
    color: COLORS.subtext,
    textAlign: 'center',
    marginTop: 8,
    lineHeight: 18,
  },
});
