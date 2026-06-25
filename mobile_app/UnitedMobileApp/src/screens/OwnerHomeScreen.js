/**
 * OwnerHomeScreen — root screen for standalone owner access (no Flask needed).
 * 3 tiles: Dashboard, Today's Sales, Balances.
 * Header has a Logout button that clears owner session and resets to Login.
 */

import React, {useLayoutEffect} from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  StatusBar,
  ScrollView,
} from 'react-native';
import {clearOwnerPin} from '../ownerSession';

const COLORS = {
  bg: '#ECEFF1',
  primary: '#263238',
  tileA: '#1565C0',
  tileB: '#37474F',
  tileC: '#004D40',
  tileD: '#4527A0',
};

const TILES = [
  {
    label: 'Dashboard',
    sub: "Today's sales, purchases & profit",
    color: COLORS.tileA,
    dest: 'OwnerDashboard',
  },
  {
    label: "Today's Sales",
    sub: 'Breakdown by brand and model',
    color: COLORS.tileB,
    dest: 'OwnerTodaySales',
  },
  {
    label: 'Balances',
    sub: 'Suppliers, customers, bank & cash',
    color: COLORS.tileC,
    dest: 'OwnerBalances',
  },
  {
    label: "Today's Digest",
    sub: 'Profit, net cash, credit & discounts',
    color: COLORS.tileD,
    dest: 'OwnerTodayDigest',
  },
];

export default function OwnerHomeScreen({navigation}) {
  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <TouchableOpacity
          style={styles.logoutBtn}
          onPress={() => {
            clearOwnerPin();
            navigation.reset({index: 0, routes: [{name: 'Login'}]});
          }}
          activeOpacity={0.7}>
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>
      ),
    });
  }, [navigation]);

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor={COLORS.primary} />
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.greeting}>Owner Panel</Text>
        {TILES.map(t => (
          <TouchableOpacity
            key={t.dest}
            style={[styles.tile, {backgroundColor: t.color}]}
            onPress={() => navigation.navigate(t.dest)}
            activeOpacity={0.83}>
            <Text style={styles.tileLabel}>{t.label}</Text>
            <Text style={styles.tileSub}>{t.sub}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: COLORS.bg},
  scroll: {
    padding: 20,
    paddingTop: 28,
  },
  greeting: {
    fontSize: 13,
    color: '#78909C',
    fontWeight: '600',
    letterSpacing: 1,
    textTransform: 'uppercase',
    marginBottom: 20,
  },
  tile: {
    borderRadius: 14,
    paddingHorizontal: 24,
    paddingVertical: 28,
    marginBottom: 16,
    elevation: 3,
    shadowColor: '#000',
    shadowOpacity: 0.15,
    shadowRadius: 6,
    shadowOffset: {width: 0, height: 3},
  },
  tileLabel: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 6,
  },
  tileSub: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.72)',
  },
  logoutBtn: {
    marginRight: 16,
    paddingVertical: 4,
    paddingHorizontal: 8,
  },
  logoutText: {
    color: '#fff',
    fontSize: 14,
  },
});
