/**
 * BarcodeScanner — full-screen camera modal for scanning IMEI barcodes.
 * Uses react-native-camera-kit for zero-dependency barcode scanning.
 *
 * Props:
 *   visible   {boolean}  – show/hide the modal
 *   onScanned {function} – called with a 15-digit string when a valid IMEI is read
 *   onClose   {function} – called when the user taps Cancel
 */

import React, {useState, useRef, useEffect} from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Modal,
  Alert,
  PermissionsAndroid,
  Platform,
} from 'react-native';
import {Camera} from 'react-native-camera-kit';

export async function requestCameraPermission() {
  if (Platform.OS === 'android') {
    try {
      const granted = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.CAMERA,
        {
          title: 'Camera Permission',
          message: 'Camera permission is required to scan barcodes.',
          buttonPositive: 'Allow',
          buttonNegative: 'Deny',
        },
      );
      return granted === PermissionsAndroid.RESULTS.GRANTED;
    } catch {
      return false;
    }
  }
  return true; // iOS permissions are handled by the library
}

export default function BarcodeScanner({visible, onScanned, onClose}) {
  const [torch, setTorch] = useState(false);
  const [invalidMsg, setInvalidMsg] = useState('');
  const lastScanTs = useRef(0);

  useEffect(() => {
    if (!visible) {
      setTorch(false);
      setInvalidMsg('');
      lastScanTs.current = 0;
    }
  }, [visible]);

  const handleBarcode = (event) => {
    if (!visible) return;

    // Debounce: ignore repeat scans within 1.5 s
    const now = Date.now();
    if (now - lastScanTs.current < 1500) return;
    lastScanTs.current = now;

    const raw = (event?.nativeEvent?.codeStringValue || '').trim();
    const digits = raw.replace(/\D/g, '');

    if (digits.length === 15) {
      onScanned(digits);
    } else {
      setInvalidMsg('Invalid IMEI — try again');
      setTimeout(() => setInvalidMsg(''), 2000);
    }
  };

  return (
    <Modal
      visible={visible}
      animationType="slide"
      statusBarTranslucent
      onRequestClose={onClose}>
      <View style={s.root}>
        {/* Live camera with built-in scan frame */}
        <Camera
          style={StyleSheet.absoluteFill}
          scanBarcode
          onReadCode={handleBarcode}
          showFrame
          frameColor="rgba(255,255,255,0.85)"
          laserColor="rgba(59,130,246,0.9)"
          torchMode={torch ? 'on' : 'off'}
          cameraType="back"
        />

        {/* Instruction / feedback text — sits below the built-in frame */}
        <View style={s.hintArea} pointerEvents="none">
          <Text style={s.hintText}>Point at IMEI barcode</Text>
          {!!invalidMsg && (
            <View style={s.toast}>
              <Text style={s.toastText}>{invalidMsg}</Text>
            </View>
          )}
        </View>

        {/* Cancel button — top-right */}
        <TouchableOpacity style={s.cancelBtn} onPress={onClose}>
          <Text style={s.cancelText}>✕  Cancel</Text>
        </TouchableOpacity>

        {/* Torch toggle — bottom-right */}
        <TouchableOpacity
          style={s.torchBtn}
          onPress={() => setTorch(t => !t)}>
          <Text style={s.torchIcon}>{torch ? '🔦' : '💡'}</Text>
          <Text style={s.torchLabel}>{torch ? 'Torch On' : 'Torch Off'}</Text>
        </TouchableOpacity>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#000',
  },

  hintArea: {
    position: 'absolute',
    bottom: '28%',
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  hintText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
    backgroundColor: 'rgba(0,0,0,0.5)',
    paddingHorizontal: 18,
    paddingVertical: 6,
    borderRadius: 20,
    overflow: 'hidden',
  },
  toast: {
    marginTop: 12,
    backgroundColor: '#C62828',
    paddingHorizontal: 20,
    paddingVertical: 8,
    borderRadius: 20,
  },
  toastText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },

  cancelBtn: {
    position: 'absolute',
    top: Platform.OS === 'android' ? 44 : 56,
    right: 20,
    backgroundColor: 'rgba(0,0,0,0.55)',
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: 24,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.35)',
  },
  cancelText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '700',
  },

  torchBtn: {
    position: 'absolute',
    bottom: 48,
    right: 24,
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.55)',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.25)',
  },
  torchIcon: {
    fontSize: 22,
  },
  torchLabel: {
    color: '#ddd',
    fontSize: 11,
    marginTop: 3,
  },
});
