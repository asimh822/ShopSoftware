/**
 * LoginScreen — 4-digit PIN keypad for salesman login.
 * Auto-submits when 4 digits entered.
 * Shake animation on wrong PIN.
 */

import React, {useState, useRef} from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Animated,
  Alert,
  StatusBar,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {apiLogin, saveSession} from '../config/api';

const COLORS = {
  primary: '#1565C0',
  primaryDark: '#0D47A1',
  danger: '#C62828',
  bg: '#1565C0',
  keyBg: '#FFFFFF',
  keyText: '#212121',
  keySpecial: 'rgba(255,255,255,0.15)',
  dot: '#FFFFFF',
  dotEmpty: 'rgba(255,255,255,0.35)',
};

const KEYS = [
  ['1', '2', '3'],
  ['4', '5', '6'],
  ['7', '8', '9'],
  ['', '0', 'DEL'],
];

export default function LoginScreen({navigation}) {
  const [pin, setPin] = useState('');
  const [loading, setLoading] = useState(false);
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

  const handleKey = async (key) => {
    if (loading) return;

    if (key === 'DEL') {
      setPin(p => p.slice(0, -1));
      return;
    }
    if (key === '') return; // blank placeholder key

    const newPin = pin + key;
    setPin(newPin);

    if (newPin.length === 4) {
      await doLogin(newPin);
    }
  };

  const doLogin = async (p) => {
    setLoading(true);
    try {
      const data = await apiLogin(p);
      if (data.success) {
        await saveSession(data.token, data.salesman.id, data.salesman.name);
        navigation.replace('Home');
      } else {
        shake();
        setPin('');
      }
    } catch (err) {
      shake();
      setPin('');
      if (err.message !== 'SESSION_EXPIRED') {
        // Show network errors, not auth failures (those are handled by shake)
        if (err.response?.status !== 401) {
          Alert.alert('Error', err.message || 'Connection failed.');
        }
      }
    } finally {
      setLoading(false);
    }
  };

  const handleChangeServer = async () => {
    Alert.alert(
      'Change Server',
      'This will take you back to Server Setup.',
      [
        {text: 'Cancel', style: 'cancel'},
        {
          text: 'Continue',
          // Keep server_url so SetupScreen can pre-fill it for editing
          onPress: () => navigation.replace('Setup'),
        },
      ],
    );
  };

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor={COLORS.bg} />

      <Text style={styles.shopName}>United Mobile</Text>
      <Text style={styles.shopSub}>Salesman Login</Text>

      {/* PIN dots */}
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

      <Text style={styles.pinHint}>Enter your 4-digit PIN</Text>

      {/* Keypad */}
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

      <TouchableOpacity style={styles.changeServer} onPress={handleChangeServer}>
        <Text style={styles.changeServerText}>Change Server</Text>
      </TouchableOpacity>
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
  shopName: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 4,
  },
  shopSub: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.7)',
    marginBottom: 40,
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
  pinHint: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.6)',
    marginBottom: 36,
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
  changeServer: {
    marginTop: 32,
    padding: 10,
  },
  changeServerText: {
    color: 'rgba(255,255,255,0.55)',
    fontSize: 13,
    textDecorationLine: 'underline',
  },
});
