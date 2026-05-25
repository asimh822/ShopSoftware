/**
 * HomeScreen — 2×2 tile menu + logout button.
 */

import React, {useEffect, useState} from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Alert,
  StatusBar,
  SafeAreaView,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {clearSession, getSalesmanName} from '../config/api';

const TILES = [
  {
    key: 'NewSale',
    label: 'New Sale',
    icon: '🛒',
    color: '#1565C0',
    darkColor: '#0D47A1',
  },
  {
    key: 'NewPurchase',
    label: 'New Purchase',
    icon: '📦',
    color: '#2E7D32',
    darkColor: '#1B5E20',
  },
  {
    key: 'StockCheck',
    label: 'Stock Check',
    icon: '🔍',
    color: '#E65100',
    darkColor: '#BF360C',
  },
  {
    key: 'MyToday',
    label: "Today's Summary",
    icon: '📊',
    color: '#6A1B9A',
    darkColor: '#4A148C',
  },
];

export default function HomeScreen({navigation}) {
  const [salesmanName, setSalesmanName] = useState('');

  useEffect(() => {
    getSalesmanName().then(n => setSalesmanName(n || ''));
  }, []);

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

  const handleTile = (key) => {
    navigation.navigate(key);
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#1565C0" />

      <View style={styles.header}>
        <View>
          <Text style={styles.welcome}>Welcome back,</Text>
          <Text style={styles.name}>{salesmanName}</Text>
        </View>
        <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.grid}>
        {TILES.map(tile => (
          <TouchableOpacity
            key={tile.key}
            style={[styles.tile, {backgroundColor: tile.color}]}
            onPress={() => handleTile(tile.key)}
            activeOpacity={0.8}>
            <Text style={styles.tileIcon}>{tile.icon}</Text>
            <Text style={styles.tileLabel}>{tile.label}</Text>
          </TouchableOpacity>
        ))}
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
  grid: {
    flex: 1,
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
  footer: {
    textAlign: 'center',
    color: '#9E9E9E',
    fontSize: 12,
    paddingBottom: 16,
  },
});
