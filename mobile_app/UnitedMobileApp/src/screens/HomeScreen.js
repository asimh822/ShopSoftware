/**
 * HomeScreen — 2×2 tile menu + refresh button + logout.
 */

import React, {useEffect, useRef, useState} from 'react';
import {
  Animated,
  ActivityIndicator,
  Alert,
  SafeAreaView,
  StatusBar,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import {clearSession, getSalesmanName, apiGet} from '../config/api';

const TILES = [
  {key: 'NewSale',     label: 'New Sale',         icon: '🛒', color: '#1565C0', darkColor: '#0D47A1'},
  {key: 'NewPurchase', label: 'New Purchase',      icon: '📦', color: '#2E7D32', darkColor: '#1B5E20'},
  {key: 'StockCheck',  label: 'Stock Check',       icon: '🔍', color: '#E65100', darkColor: '#BF360C'},
  {key: 'MyToday',     label: "Today's Summary",   icon: '📊', color: '#6A1B9A', darkColor: '#4A148C'},
];

function formatPkr(amount) {
  return amount.toLocaleString('en-PK', {maximumFractionDigits: 0});
}

export default function HomeScreen({navigation}) {
  const [salesmanName, setSalesmanName] = useState('');
  const [cashInHand, setCashInHand]     = useState(null);  // null=loading, false=error, number=ok
  const [cashLoading, setCashLoading]   = useState(true);
  const [refreshing, setRefreshing]     = useState(false);

  const spinAnim = useRef(new Animated.Value(0)).current;
  const spinRef  = useRef(null);

  const startSpin = () => {
    spinAnim.setValue(0);
    spinRef.current = Animated.loop(
      Animated.timing(spinAnim, {
        toValue: 1,
        duration: 600,
        useNativeDriver: true,
      }),
    );
    spinRef.current.start();
  };

  const stopSpin = () => {
    if (spinRef.current) {
      spinRef.current.stop();
      spinRef.current = null;
    }
    spinAnim.setValue(0);
  };

  const spin = spinAnim.interpolate({
    inputRange:  [0, 1],
    outputRange: ['0deg', '360deg'],
  });

  // ── Shared refresh function ────────────────────────────────────────────────
  // Fetches all data shown on or pre-loaded for the Home screen.
  // Call on mount and when the refresh button is tapped.
  const refreshData = async () => {
    setCashLoading(true);
    try {
      // Fetch in parallel — cash_in_hand is displayed; others are background
      // prefetches so child screens benefit from warmed server-side caches.
      const [cashResult] = await Promise.allSettled([
        apiGet('/api/cash_in_hand'),
        apiGet('/api/stock'),
        apiGet('/api/brands'),
        apiGet('/api/customers/list'),
        apiGet('/api/suppliers'),
      ]);

      if (cashResult.status === 'fulfilled' && cashResult.value?.success) {
        setCashInHand(cashResult.value.cash_in_hand);
      } else {
        setCashInHand(false);
      }
    } catch (err) {
      if (err.message === 'SESSION_EXPIRED') {
        navigation.replace('Login');
        return;
      }
      setCashInHand(false);
    } finally {
      setCashLoading(false);
    }
  };

  useEffect(() => {
    getSalesmanName().then(n => setSalesmanName(n || ''));
    refreshData();
  }, []);

  // ── Refresh button handler ─────────────────────────────────────────────────
  const handleRefresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    startSpin();
    try {
      await refreshData();
    } finally {
      stopSpin();
      setRefreshing(false);
    }
  };

  const handleLogout = () => {
    Alert.alert('Logout', 'Are you sure you want to logout?', [
      {text: 'Cancel', style: 'cancel'},
      {
        text: 'Logout',
        style: 'destructive',
        onPress: async () => {
          await clearSession();
          navigation.replace('Login');
        },
      },
    ]);
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#1565C0" />

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <View style={styles.header}>
        <View>
          <Text style={styles.welcome}>Welcome back,</Text>
          <Text style={styles.name}>{salesmanName}</Text>
        </View>

        <View style={styles.headerRight}>
          {/* Refresh button */}
          <TouchableOpacity
            style={styles.refreshBtn}
            onPress={handleRefresh}
            disabled={refreshing}
            activeOpacity={0.75}>
            <Animated.View style={{transform: [{rotate: spin}]}}>
              <MaterialIcons name="refresh" size={22} color="#fff" />
            </Animated.View>
          </TouchableOpacity>

          {/* Logout button */}
          <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
            <Text style={styles.logoutText}>Logout</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* ── Body ───────────────────────────────────────────────────────────── */}
      <View style={styles.body}>
        <View style={styles.grid}>
          {TILES.map(tile => (
            <TouchableOpacity
              key={tile.key}
              style={[styles.tile, {backgroundColor: tile.color}]}
              onPress={() => navigation.navigate(tile.key)}
              activeOpacity={0.8}>
              <Text style={styles.tileIcon}>{tile.icon}</Text>
              <Text style={styles.tileLabel}>{tile.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={styles.cashCard}>
          <Text style={styles.cashLabel}>Cash in Hand</Text>
          {cashLoading ? (
            <ActivityIndicator size="small" color="#1565C0" />
          ) : (
            <Text style={styles.cashAmount}>
              {cashInHand === false ? '—' : `Rs. ${formatPkr(cashInHand)}`}
            </Text>
          )}
        </View>
      </View>

      <Text style={styles.footer}>United Mobile • Multan</Text>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F5F5F5',
  },
  header: {
    backgroundColor: '#1565C0',
    paddingHorizontal: 20,
    paddingVertical: 20,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  welcome: {
    color: 'rgba(255,255,255,0.75)',
    fontSize: 13,
  },
  name: {
    color: '#fff',
    fontSize: 20,
    fontWeight: 'bold',
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  refreshBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(255,255,255,0.2)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  logoutBtn: {
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.6)',
    borderRadius: 6,
    paddingHorizontal: 14,
    paddingVertical: 6,
  },
  logoutText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },
  body: {
    flex: 1,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    padding: 16,
    paddingTop: 24,
    alignContent: 'flex-start',
  },
  tile: {
    width: '45%',
    margin: '2%',
    aspectRatio: 1,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 4,
    shadowColor: '#000',
    shadowOpacity: 0.2,
    shadowRadius: 6,
    shadowOffset: {width: 0, height: 3},
  },
  tileIcon: {
    fontSize: 42,
    marginBottom: 10,
  },
  tileLabel: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
    textAlign: 'center',
  },
  cashCard: {
    marginHorizontal: 20,
    marginTop: 4,
    backgroundColor: '#fff',
    borderRadius: 12,
    paddingHorizontal: 20,
    paddingVertical: 14,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    elevation: 3,
    shadowColor: '#000',
    shadowOpacity: 0.1,
    shadowRadius: 4,
    shadowOffset: {width: 0, height: 2},
  },
  cashLabel: {
    fontSize: 14,
    color: '#616161',
    fontWeight: '500',
  },
  cashAmount: {
    fontSize: 18,
    color: '#1565C0',
    fontWeight: 'bold',
  },
  footer: {
    textAlign: 'center',
    color: '#9E9E9E',
    fontSize: 12,
    paddingVertical: 16,
  },
});
