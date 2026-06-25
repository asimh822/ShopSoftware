/**
 * OwnerPinScreen — 4-digit PIN gate for owner-only features.
 *
 * Two verification paths based on destination:
 *   'OwnerHome'    → verify against Supabase settings (standalone, no Flask)
 *   anything else  → verify against Flask /api/owner/dashboard (salesman-flow)
 */

import React, {useState, useRef} from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Animated,
  StatusBar,
} from 'react-native';
import {apiOwnerGet} from '../config/api';
import {setOwnerPin} from '../ownerSession';
import {SUPABASE_URL, SUPABASE_KEY} from '../supabaseConfig';

const SB_HEADERS = {
  apikey: SUPABASE_KEY,
  Authorization: `Bearer ${SUPABASE_KEY}`,
  'Content-Type': 'application/json',
};

const COLORS = {
  bg: '#263238',
  keyBg: '#FFFFFF',
  keyText: '#212121',
  keySpecial: 'rgba(255,255,255,0.15)',
  dot: '#FFFFFF',
  dotEmpty: 'rgba(255,255,255,0.35)',
  error: '#EF9A9A',
};

const KEYS = [
  ['1', '2', '3'],
  ['4', '5', '6'],
  ['7', '8', '9'],
  ['', '0', 'DEL'],
];

export default function OwnerPinScreen({navigation, route}) {
  const {destination} = route.params || {};
  const [pin, setPin] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const shakeAnim = useRef(new Animated.Value(0)).current;

  const shake = () => {
    Animated.sequence([
      Animated.timing(shakeAnim, {toValue: 12, duration: 60, useNativeDriver: true}),
      Animated.timing(shakeAnim, {toValue: -12, duration: 60, useNativeDriver: true}),
      Animated.timing(shakeAnim, {toValue: 10, duration: 60, useNativeDriver: true}),
      Animated.timing(shakeAnim, {toValue: -10, duration: 60, useNativeDriver: true}),
      Animated.timing(shakeAnim, {toValue: 0, duration: 60, useNativeDriver: true}),
    ]).start();
  };

  const handleKey = async key => {
    if (loading) return;
    if (key === 'DEL') {
      setPin(p => p.slice(0, -1));
      setErrorMsg('');
      return;
    }
    if (key === '') return;

    const newPin = pin + key;
    setPin(newPin);
    if (newPin.length === 4) {
      await doVerify(newPin);
    }
  };

  const doVerify = async p => {
    setLoading(true);
    setErrorMsg('');
    try {
      if (destination === 'OwnerHome') {
        // Standalone owner flow — verify against Supabase (no Flask/WiFi needed)
        const res = await fetch(
          `${SUPABASE_URL}/rest/v1/settings?key=eq.owner_pin&select=value`,
          {headers: SB_HEADERS},
        );
        const data = await res.json();
        if (!Array.isArray(data)) {
          // 404 = settings table not created in Supabase yet
          throw new Error(data?.code === '42P01' ? 'TABLE_MISSING' : 'CONNECTION_ERROR');
        }
        const storedPin = data[0]?.value;
        if (!storedPin) throw new Error('PIN_NOT_CONFIGURED');
        if (p !== storedPin) throw new Error('OWNER_AUTH_FAILED');
        setOwnerPin(p);
        navigation.reset({index: 0, routes: [{name: 'OwnerHome'}]});
      } else {
        // Salesman-accessed owner flow — verify against Flask
        await apiOwnerGet('/api/owner/dashboard', p);
        setOwnerPin(p);
        navigation.replace(destination || 'OwnerDashboard');
      }
    } catch (err) {
      shake();
      setPin('');
      if (err.message === 'OWNER_AUTH_FAILED') {
        setErrorMsg('Incorrect PIN');
      } else if (err.message === 'PIN_NOT_CONFIGURED') {
        setErrorMsg('PIN not set — run Supabase SQL');
      } else if (err.message === 'TABLE_MISSING') {
        setErrorMsg('Run settings SQL in Supabase first');
      } else {
        setErrorMsg(
          destination === 'OwnerHome' ? 'No internet connection' : 'Connection error',
        );
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor={COLORS.bg} />

      <Text style={styles.title}>Owner Access</Text>
      <Text style={styles.subtitle}>Enter your 4-digit PIN</Text>

      <Animated.View
        style={[styles.dotsRow, {transform: [{translateX: shakeAnim}]}]}>
        {[0, 1, 2, 3].map(i => (
          <View
            key={i}
            style={[
              styles.dot,
              i < pin.length ? styles.dotFilled : styles.dotEmpty,
            ]}
          />
        ))}
      </Animated.View>

      {errorMsg ? (
        <Text style={styles.errorText}>{errorMsg}</Text>
      ) : (
        <View style={styles.errorPlaceholder} />
      )}

      {loading ? (
        <View style={styles.loadingArea}>
          <ActivityIndicator size="large" color="#fff" />
          <Text style={styles.loadingText}>Verifying...</Text>
        </View>
      ) : (
        <View style={styles.keypad}>
          {KEYS.map((row, ri) => (
            <View key={ri} style={styles.keyRow}>
              {row.map((key, ki) => (
                <TouchableOpacity
                  key={ki}
                  style={[
                    styles.key,
                    key === '' && styles.keyHidden,
                    key === 'DEL' && styles.keyDel,
                  ]}
                  onPress={() => handleKey(key)}
                  disabled={key === '' || loading}
                  activeOpacity={0.7}>
                  {key === 'DEL' ? (
                    <Text style={[styles.keyText, styles.keyDelText]}>⌫</Text>
                  ) : (
                    <Text style={styles.keyText}>{key}</Text>
                  )}
                </TouchableOpacity>
              ))}
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bg,
    alignItems: 'center',
    justifyContent: 'center',
    paddingBottom: 30,
  },
  title: {
    fontSize: 26,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.6)',
    marginBottom: 36,
  },
  dotsRow: {
    flexDirection: 'row',
    marginBottom: 12,
  },
  dot: {
    width: 18,
    height: 18,
    borderRadius: 9,
    marginHorizontal: 10,
  },
  dotFilled: {backgroundColor: COLORS.dot},
  dotEmpty: {backgroundColor: COLORS.dotEmpty},
  errorText: {
    fontSize: 13,
    color: COLORS.error,
    marginBottom: 24,
    fontWeight: '600',
  },
  errorPlaceholder: {
    height: 13 + 24,
  },
  loadingArea: {
    height: 240,
    alignItems: 'center',
    justifyContent: 'center',
  },
  loadingText: {
    color: '#fff',
    marginTop: 12,
    fontSize: 15,
  },
  keypad: {
    width: 280,
  },
  keyRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 16,
  },
  key: {
    width: 82,
    height: 64,
    backgroundColor: COLORS.keyBg,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 3,
    shadowColor: '#000',
    shadowOpacity: 0.2,
    shadowRadius: 4,
    shadowOffset: {width: 0, height: 2},
  },
  keyHidden: {
    backgroundColor: 'transparent',
    elevation: 0,
    shadowOpacity: 0,
  },
  keyDel: {
    backgroundColor: COLORS.keySpecial,
    elevation: 0,
  },
  keyText: {
    fontSize: 26,
    fontWeight: '600',
    color: COLORS.keyText,
  },
  keyDelText: {
    color: '#fff',
    fontSize: 22,
  },
});
