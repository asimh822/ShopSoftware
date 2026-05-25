/**
 * SetupScreen — configure server URL and test connection.
 * Shown only when no server_url is saved in AsyncStorage.
 */

import React, {useState, useEffect} from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {apiHealth} from '../config/api';

const COLORS = {
  primary: '#1565C0',
  success: '#2E7D32',
  danger: '#C62828',
  bg: '#F5F5F5',
  card: '#FFFFFF',
  border: '#BDBDBD',
  text: '#212121',
  subtext: '#757575',
};

export default function SetupScreen({navigation}) {
  const [url, setUrl] = useState('');

  // Pre-fill with any saved URL so the user doesn't have to retype it
  useEffect(() => {
    AsyncStorage.getItem('server_url').then(saved => {
      if (saved) setUrl(saved);
    });
  }, []);
  const [testing, setTesting] = useState(false);
  const [status, setStatus] = useState(null); // null | 'ok' | 'fail'
  const [statusMsg, setStatusMsg] = useState('');

  const handleTest = async () => {
    const trimmed = url.trim();
    if (!trimmed || trimmed === 'http://' || !trimmed.startsWith('http')) {
      Alert.alert('Required', 'Please enter the server URL (e.g. http://192.168.x.x:5000).');
      return;
    }

    setTesting(true);
    setStatus(null);
    setStatusMsg('');

    try {
      // Pass URL directly — no token needed, /api/health is fully public.
      // apiHealth uses validateStatus:()=>true so any HTTP reply = server reachable.
      const data = await apiHealth(trimmed);
      setStatus('ok');
      setStatusMsg(
        (data && (data.message || data.status))
          ? `${data.message || data.status}`
          : 'Server is reachable!',
      );
    } catch (err) {
      // Only lands here on true network failure (no route, timeout, DNS fail)
      setStatus('fail');
      setStatusMsg('Cannot reach server. Check the URL and Wi-Fi connection.');
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    if (status !== 'ok') {
      Alert.alert('Test First', 'Please test the connection before saving.');
      return;
    }
    await AsyncStorage.setItem('server_url', url.trim());
    navigation.replace('Login');
  };

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled">
        <View style={styles.card}>
          <Text style={styles.title}>Server Setup</Text>
          <Text style={styles.subtitle}>
            Enter the URL of the United Mobile API server running on your PC.
          </Text>

          <Text style={styles.label}>Server URL</Text>
          <TextInput
            style={styles.input}
            value={url}
            onChangeText={setUrl}
            placeholder="http://192.168.1.x:5000"
            placeholderTextColor={COLORS.subtext}
            keyboardType="url"
            autoCapitalize="none"
            autoCorrect={false}
          />

          <Text style={styles.hint}>
            Example: http://192.168.1.100:5000{'\n'}
            Use your PC's local IP address. Both devices must be on the same
            Wi-Fi network.
          </Text>

          <TouchableOpacity
            style={[styles.btn, styles.btnOutline]}
            onPress={handleTest}
            disabled={testing}>
            {testing ? (
              <ActivityIndicator color={COLORS.primary} />
            ) : (
              <Text style={styles.btnOutlineText}>Test Connection</Text>
            )}
          </TouchableOpacity>

          {status !== null && (
            <View
              style={[
                styles.statusBox,
                status === 'ok' ? styles.statusOk : styles.statusFail,
              ]}>
              <Text
                style={[
                  styles.statusText,
                  status === 'ok' ? styles.statusTextOk : styles.statusTextFail,
                ]}>
                {status === 'ok' ? '✓ ' : '✗ '}
                {statusMsg}
              </Text>
            </View>
          )}

          <TouchableOpacity
            style={[
              styles.btn,
              styles.btnPrimary,
              status !== 'ok' && styles.btnDisabled,
            ]}
            onPress={handleSave}
            disabled={status !== 'ok'}>
            <Text style={styles.btnPrimaryText}>Save & Continue</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: {flex: 1, backgroundColor: COLORS.bg},
  container: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 20,
  },
  card: {
    backgroundColor: COLORS.card,
    borderRadius: 12,
    padding: 24,
    elevation: 3,
    shadowColor: '#000',
    shadowOpacity: 0.1,
    shadowRadius: 6,
    shadowOffset: {width: 0, height: 2},
  },
  title: {
    fontSize: 22,
    fontWeight: 'bold',
    color: COLORS.primary,
    marginBottom: 8,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 14,
    color: COLORS.subtext,
    textAlign: 'center',
    marginBottom: 24,
    lineHeight: 20,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: 6,
  },
  input: {
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 8,
    padding: 12,
    fontSize: 15,
    color: COLORS.text,
    marginBottom: 10,
  },
  hint: {
    fontSize: 12,
    color: COLORS.subtext,
    marginBottom: 20,
    lineHeight: 18,
  },
  btn: {
    borderRadius: 8,
    padding: 14,
    alignItems: 'center',
    marginTop: 10,
  },
  btnPrimary: {backgroundColor: COLORS.primary},
  btnPrimaryText: {color: '#fff', fontWeight: 'bold', fontSize: 16},
  btnOutline: {
    borderWidth: 2,
    borderColor: COLORS.primary,
    backgroundColor: 'transparent',
  },
  btnOutlineText: {color: COLORS.primary, fontWeight: 'bold', fontSize: 15},
  btnDisabled: {opacity: 0.4},
  statusBox: {
    borderRadius: 8,
    padding: 12,
    marginTop: 12,
  },
  statusOk: {backgroundColor: '#E8F5E9'},
  statusFail: {backgroundColor: '#FFEBEE'},
  statusText: {fontSize: 14, fontWeight: '500'},
  statusTextOk: {color: COLORS.success},
  statusTextFail: {color: COLORS.danger},
});
