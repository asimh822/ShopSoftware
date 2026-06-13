/**
 * NewSaleScreen — record a sale on mobile.
 *
 * Cash flow:
 *  1. Enter Contact Number (11-digit, 03xxxxxxxx) — auto-looks up customer on complete entry
 *     If found → auto-fills Name + shows Welcome Back popup
 *  2. Enter Customer Name (mandatory)
 *  3. IMEI search → add lines → save
 *  Payment is always cash — full amount, no selector.
 *
 * Credit flow:
 *  1. Select credit customer from searchable dropdown (loads /api/customers/list)
 *  2. IMEI search → add lines → save
 *  No payment collected — goes to customer ledger as receivable.
 */

import React, {useState, useEffect, useRef} from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  FlatList,
  Modal,
} from 'react-native';
import {apiGet, apiPost, getSalesmanId} from '../config/api';
import {fmtPKR, todayDDMMYYYY, isValidPakistaniPhone, titleCase} from '../utils/formatting';
import BarcodeScanner, {requestCameraPermission} from '../components/BarcodeScanner';

const COLORS = {
  primary: '#1565C0',
  success: '#2E7D32',
  danger: '#C62828',
  bg: '#F5F5F5',
  card: '#FFFFFF',
  border: '#E0E0E0',
  text: '#212121',
  subtext: '#757575',
  cashTab: '#1565C0',
  creditTab: '#2E7D32',
};

export default function NewSaleScreen({navigation}) {
  const [saleType, setSaleType] = useState('cash'); // 'cash' | 'credit'

  // ── Cash customer fields ──────────────────────────────────────────────────
  const [cashPhone, setCashPhone] = useState('');
  const [cashName, setCashName] = useState('');
  const [lookingUpCashCustomer, setLookingUpCashCustomer] = useState(false);

  // ── Credit customer dropdown ──────────────────────────────────────────────
  const [creditCustomers, setCreditCustomers] = useState([]);
  const [loadingCreditCustomers, setLoadingCreditCustomers] = useState(false);
  const [creditCustomer, setCreditCustomer] = useState(null);
  const [creditPickerVisible, setCreditPickerVisible] = useState(false);
  const [creditSearch, setCreditSearch] = useState('');

  // ── IMEI search ───────────────────────────────────────────────────────────
  const [imeiInput, setImeiInput] = useState('');
  const [imeiResults, setImeiResults] = useState([]);
  const [searchingImei, setSearchingImei] = useState(false);
  const imeiDebounce = useRef(null);

  // ── Sale lines ────────────────────────────────────────────────────────────
  const [lines, setLines] = useState([]);
  const [discount, setDiscount] = useState('0');

  // ── Barcode scanner ───────────────────────────────────────────────────────
  const [scannerVisible, setScannerVisible] = useState(false);

  const openScanner = async () => {
    const granted = await requestCameraPermission();
    if (granted) {
      setScannerVisible(true);
    } else {
      Alert.alert(
        'Permission Required',
        'Camera permission is required to scan barcodes. Please enable it in Settings.',
      );
    }
  };

  const handleScanned = (digits) => {
    setScannerVisible(false);
    onImeiChange(digits);
  };

  // ── Submission ────────────────────────────────────────────────────────────
  const [saving, setSaving] = useState(false);

  const today = todayDDMMYYYY();

  // Load credit customers when switching to credit tab
  useEffect(() => {
    if (saleType === 'credit' && creditCustomers.length === 0) {
      loadCreditCustomers();
    }
  }, [saleType]);

  // ── Credit customers ──────────────────────────────────────────────────────

  const loadCreditCustomers = async () => {
    setLoadingCreditCustomers(true);
    try {
      const data = await apiGet('/api/customers/list');
      setCreditCustomers(data.customers || []);
    } catch (err) {
      if (err.message === 'SESSION_EXPIRED') {
        navigation.replace('Login');
      } else {
        Alert.alert('Error', 'Failed to load customers. Check connection.');
      }
    } finally {
      setLoadingCreditCustomers(false);
    }
  };

  const filteredCreditCustomers = creditCustomers.filter(c => {
    if (!creditSearch.trim()) return true;
    const q = creditSearch.toLowerCase();
    return (
      c.name.toLowerCase().includes(q) ||
      (c.contact || '').includes(creditSearch.trim())
    );
  });

  // ── Cash customer phone auto-lookup ───────────────────────────────────────

  const handleCashPhoneChange = (text) => {
    setCashPhone(text);
    if (text.length === 11 && isValidPakistaniPhone(text)) {
      doLookupCashCustomer(text);
    }
  };

  const doLookupCashCustomer = async (phone) => {
    setLookingUpCashCustomer(true);
    try {
      const data = await apiGet('/api/customers/search', {phone});
      if (data.found && data.customer && data.customer.name) {
        const c = data.customer;
        setCashName(c.name);
        const lastMsg = c.last_sale
          ? `Last purchase: ${c.last_sale.model}\nDate: ${c.last_sale.date}\nAmount: PKR ${fmtPKR(c.last_sale.amount)}`
          : '';
        Alert.alert(`Welcome back, ${c.name}!`, lastMsg || 'Customer found.');
      }
    } catch (err) {
      if (err.message === 'SESSION_EXPIRED') navigation.replace('Login');
      // silently ignore other errors — customer just won't be pre-filled
    } finally {
      setLookingUpCashCustomer(false);
    }
  };

  // ── IMEI search ───────────────────────────────────────────────────────────

  const onImeiChange = (text) => {
    setImeiInput(text);
    setImeiResults([]);
    if (imeiDebounce.current) clearTimeout(imeiDebounce.current);
    if (text.length < 5) return;
    imeiDebounce.current = setTimeout(() => {
      searchImei(text);
    }, 400);
  };

  const searchImei = async (digits) => {
    setSearchingImei(true);
    try {
      const data = await apiGet('/api/imei/search', {digits});
      const addedImeis = lines.map(l => l.imei);
      setImeiResults((data.results || []).filter(r => !addedImeis.includes(r.imei)));
    } catch (err) {
      if (err.message === 'SESSION_EXPIRED') navigation.replace('Login');
    } finally {
      setSearchingImei(false);
    }
  };

  const addLine = (item) => {
    setLines(prev => [
      ...prev,
      {
        imei: item.imei,
        model: item.model,
        brandModel: `${item.brand} ${item.model}`,
        referencePrice: item.reference_price,
        purchasePrice: item.purchase_price || 0,
        finalPrice: String(Math.round(item.reference_price || 0)),
        stock_item_id: item.stock_item_id,
        model_id: item.model_id,
      },
    ]);
    setImeiInput('');
    setImeiResults([]);
  };

  const removeLine = (imei) => {
    setLines(prev => prev.filter(l => l.imei !== imei));
  };

  const updateLinePrice = (imei, val) => {
    setLines(prev =>
      prev.map(l => (l.imei === imei ? {...l, finalPrice: val} : l)),
    );
  };

  // ── Totals ────────────────────────────────────────────────────────────────

  const subtotal = lines.reduce((s, l) => s + (parseFloat(l.finalPrice) || 0), 0);
  const discountAmt = parseFloat(discount) || 0;
  const total = Math.max(0, subtotal - discountAmt);

  // ── Save ──────────────────────────────────────────────────────────────────

  const handleSave = async () => {
    if (lines.length === 0) {
      Alert.alert('Empty', 'Add at least one phone to the sale.');
      return;
    }

    if (saleType === 'cash') {
      if (!cashPhone.trim() || !isValidPakistaniPhone(cashPhone)) {
        Alert.alert('Required', 'Enter a valid 11-digit contact number starting with 03.');
        return;
      }
      if (!cashName.trim()) {
        Alert.alert('Required', 'Enter customer name.');
        return;
      }
    } else {
      if (!creditCustomer) {
        Alert.alert('Required', 'Select a credit customer.');
        return;
      }
    }

    for (const l of lines) {
      const p = parseFloat(l.finalPrice);
      if (!p || p <= 0) {
        Alert.alert('Invalid Price', `Enter a valid price for IMEI ${l.imei}`);
        return;
      }
    }

    // ── Below-cost confirmation ───────────────────────────────────────────
    const belowCostLines = lines.filter(
      l => l.purchasePrice > 0 && parseFloat(l.finalPrice) < l.purchasePrice,
    );
    if (belowCostLines.length > 0) {
      const proceed = await new Promise(resolve => {
        Alert.alert(
          'Below Cost Warning',
          'One or more items are being sold below purchase price. Do you want to continue?',
          [
            {text: 'Go Back', style: 'cancel', onPress: () => resolve(false)},
            {text: 'Continue', onPress: () => resolve(true)},
          ],
          {cancelable: false},
        );
      });
      if (!proceed) return;
    }

    const salesman_id = await getSalesmanId();

    // Cash sales: always full cash payment. Credit sales: no upfront payment.
    const payment_method = saleType === 'cash' ? 'cash' : null;
    const cash_amount = saleType === 'cash' ? total : 0;

    const payload = {
      type: saleType,
      date: today,
      salesman_id: parseInt(salesman_id),
      discount: discountAmt,
      payment_method,
      cash_amount,
      bank_amount: 0,
      lines: lines.map(l => ({
        imei: l.imei,
        stock_item_id: l.stock_item_id,
        model_id: l.model_id,
        reference_price: l.referencePrice,
        final_price: parseFloat(l.finalPrice),
        discount: 0,
      })),
    };

    if (saleType === 'cash') {
      payload.cash_customer_name = titleCase(cashName);
      payload.cash_customer_contact = cashPhone.trim();
    } else {
      payload.customer_id = creditCustomer.id;
    }

    setSaving(true);
    try {
      const data = await apiPost('/api/sale', payload);
      if (data.success) {
        Alert.alert(
          'Sale Saved',
          `Invoice ${data.sv_number} created.\nTotal: PKR ${fmtPKR(total)}`,
          [{text: 'OK', onPress: () => navigation.goBack()}],
        );
      } else {
        Alert.alert('Error', data.error || 'Sale failed.');
      }
    } catch (err) {
      if (err.message === 'SESSION_EXPIRED') navigation.replace('Login');
      else Alert.alert('Error', err.message || 'Sale failed.');
    } finally {
      setSaving(false);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled">

          {/* Sale type toggle */}
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Sale Type</Text>
            <View style={styles.toggle}>
              <TouchableOpacity
                style={[
                  styles.toggleBtn,
                  saleType === 'cash' && styles.toggleBtnActiveCash,
                ]}
                onPress={() => {
                  setSaleType('cash');
                  setCreditCustomer(null);
                  setCreditSearch('');
                }}>
                <Text
                  style={[
                    styles.toggleBtnText,
                    saleType === 'cash' && styles.toggleBtnTextActive,
                  ]}>
                  Cash
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[
                  styles.toggleBtn,
                  saleType === 'credit' && styles.toggleBtnActiveCredit,
                ]}
                onPress={() => {
                  setSaleType('credit');
                  setCashName('');
                  setCashPhone('');
                }}>
                <Text
                  style={[
                    styles.toggleBtnText,
                    saleType === 'credit' && styles.toggleBtnTextActive,
                  ]}>
                  Credit
                </Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* Customer details */}
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Customer</Text>

            {saleType === 'cash' ? (
              <>
                {/* Contact Number FIRST — auto-looks up on 11-digit entry */}
                <View style={styles.phoneRow}>
                  <TextInput
                    style={[styles.input, styles.flex]}
                    placeholder="Contact Number * (03xxxxxxxxx)"
                    placeholderTextColor={COLORS.subtext}
                    value={cashPhone}
                    onChangeText={handleCashPhoneChange}
                    keyboardType="phone-pad"
                    maxLength={11}
                  />
                  {lookingUpCashCustomer && (
                    <ActivityIndicator
                      style={styles.phoneSpinner}
                      color={COLORS.primary}
                    />
                  )}
                </View>
                {/* Name field SECOND */}
                <TextInput
                  style={styles.input}
                  placeholder="Customer Name *"
                  placeholderTextColor={COLORS.subtext}
                  value={cashName}
                  onChangeText={setCashName}
                  autoCapitalize="words"
                />
              </>
            ) : (
              /* Credit: searchable dropdown */
              <>
                <TouchableOpacity
                  style={styles.pickerBtn}
                  onPress={() => {
                    setCreditSearch('');
                    setCreditPickerVisible(true);
                    if (creditCustomers.length === 0) loadCreditCustomers();
                  }}>
                  <Text
                    style={[
                      styles.pickerBtnText,
                      !creditCustomer && styles.pickerBtnPlaceholder,
                    ]}>
                    {creditCustomer ? creditCustomer.name : 'Select Credit Customer...'}
                  </Text>
                  {loadingCreditCustomers ? (
                    <ActivityIndicator size="small" color={COLORS.primary} />
                  ) : (
                    <Text style={styles.pickerArrow}>▼</Text>
                  )}
                </TouchableOpacity>

                {creditCustomer && (
                  <View style={styles.customerFound}>
                    <Text style={styles.customerFoundName}>{creditCustomer.name}</Text>
                    {!!creditCustomer.contact && (
                      <Text style={styles.customerFoundSub}>{creditCustomer.contact}</Text>
                    )}
                    <Text style={styles.customerFoundBalance}>
                      Balance: PKR {fmtPKR(creditCustomer.balance)}
                    </Text>
                  </View>
                )}
              </>
            )}
          </View>

          {/* IMEI search */}
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Add Phones (by IMEI)</Text>
            <View style={styles.row}>
              <TextInput
                style={[styles.input, styles.flex]}
                placeholder="Type last 5 digits of IMEI to search..."
                placeholderTextColor={COLORS.subtext}
                value={imeiInput}
                onChangeText={onImeiChange}
                keyboardType="number-pad"
                maxLength={15}
              />
              {searchingImei && (
                <ActivityIndicator style={styles.spinner} color={COLORS.primary} />
              )}
              <TouchableOpacity style={styles.scanBtn} onPress={openScanner}>
                <Text style={styles.scanBtnIcon}>📷</Text>
              </TouchableOpacity>
            </View>

            {imeiResults.length > 0 && (
              <View style={styles.dropdown}>
                {imeiResults.map(item => (
                  <TouchableOpacity
                    key={item.imei}
                    style={styles.dropdownItem}
                    onPress={() => addLine(item)}>
                    <Text style={styles.dropdownModel}>
                      {item.brand} {item.model}
                    </Text>
                    <Text style={styles.dropdownImei}>{item.imei}</Text>
                    <Text style={styles.dropdownPrice}>
                      PKR {fmtPKR(item.reference_price)}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}

            {imeiInput.length >= 5 && imeiResults.length === 0 && !searchingImei && (
              <Text style={styles.noResults}>
                No in-stock phone found with those digits.
              </Text>
            )}
          </View>

          {/* Sale lines */}
          {lines.length > 0 && (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Sale Items</Text>
              {lines.map(line => (
                <View key={line.imei} style={styles.lineItem}>
                  <View style={styles.lineHeader}>
                    <Text style={styles.lineModel}>{line.brandModel}</Text>
                    <TouchableOpacity onPress={() => removeLine(line.imei)}>
                      <Text style={styles.lineRemove}>✕</Text>
                    </TouchableOpacity>
                  </View>
                  <Text style={styles.lineImei}>{line.imei}</Text>
                  <View style={styles.priceRow}>
                    <Text style={styles.priceLabel}>Sale Price (PKR):</Text>
                    <TextInput
                      style={styles.priceInput}
                      value={line.finalPrice}
                      onChangeText={val => updateLinePrice(line.imei, val)}
                      keyboardType="number-pad"
                    />
                  </View>
                  {line.purchasePrice > 0 &&
                   parseFloat(line.finalPrice) > 0 &&
                   parseFloat(line.finalPrice) < line.purchasePrice && (
                    <Text style={styles.belowCostWarn}>
                      {'⚠ Selling below cost — Purchase price: Rs. ' + fmtPKR(line.purchasePrice)}
                    </Text>
                  )}
                </View>
              ))}

              <View style={styles.discountRow}>
                <Text style={styles.discountLabel}>Discount (PKR):</Text>
                <TextInput
                  style={styles.priceInput}
                  value={discount}
                  onChangeText={setDiscount}
                  keyboardType="number-pad"
                />
              </View>

              <View style={styles.totalRow}>
                <Text style={styles.totalLabel}>TOTAL</Text>
                <Text style={styles.totalAmount}>PKR {fmtPKR(total)}</Text>
              </View>
            </View>
          )}

          {/* Save button */}
          <TouchableOpacity
            style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
            onPress={handleSave}
            disabled={saving}>
            {saving ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.saveBtnText}>Save Sale</Text>
            )}
          </TouchableOpacity>

          <View style={styles.bottomPad} />
        </ScrollView>
      </KeyboardAvoidingView>

      {/* Barcode / IMEI scanner */}
      <BarcodeScanner
        visible={scannerVisible}
        onScanned={handleScanned}
        onClose={() => setScannerVisible(false)}
      />

      {/* Credit Customer Picker Modal */}
      <Modal
        visible={creditPickerVisible}
        transparent
        animationType="slide"
        onRequestClose={() => setCreditPickerVisible(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Select Customer</Text>
              <TouchableOpacity onPress={() => setCreditPickerVisible(false)}>
                <Text style={styles.modalClose}>✕</Text>
              </TouchableOpacity>
            </View>

            {/* Search input */}
            <View style={styles.modalSearch}>
              <TextInput
                style={styles.modalSearchInput}
                placeholder="Search by name or phone number..."
                placeholderTextColor={COLORS.subtext}
                value={creditSearch}
                onChangeText={setCreditSearch}
                autoCapitalize="none"
              />
            </View>

            <FlatList
              data={filteredCreditCustomers}
              keyExtractor={item => String(item.id)}
              renderItem={({item}) => (
                <TouchableOpacity
                  style={styles.modalItem}
                  onPress={() => {
                    setCreditCustomer(item);
                    setCreditPickerVisible(false);
                  }}>
                  <Text style={styles.modalItemText}>{item.name}</Text>
                  <Text style={styles.modalItemSub}>
                    {item.contact ? `${item.contact}  ·  ` : ''}
                    Balance: PKR {fmtPKR(item.balance)}
                  </Text>
                </TouchableOpacity>
              )}
              ItemSeparatorComponent={() => <View style={styles.separator} />}
              keyboardShouldPersistTaps="handled"
              ListEmptyComponent={
                <View style={styles.emptyPicker}>
                  <Text style={styles.emptyPickerText}>
                    {loadingCreditCustomers
                      ? 'Loading customers...'
                      : creditSearch
                      ? 'No customers match your search.'
                      : 'No credit customers found.'}
                  </Text>
                </View>
              }
            />
          </View>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  flex: {flex: 1},
  scroll: {flex: 1, backgroundColor: COLORS.bg},
  content: {padding: 16},
  card: {
    backgroundColor: COLORS.card,
    borderRadius: 10,
    padding: 16,
    marginBottom: 12,
    elevation: 2,
    shadowColor: '#000',
    shadowOpacity: 0.08,
    shadowRadius: 4,
    shadowOffset: {width: 0, height: 2},
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: COLORS.subtext,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 12,
  },
  toggle: {
    flexDirection: 'row',
    borderRadius: 8,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  toggleBtn: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    backgroundColor: '#F5F5F5',
  },
  toggleBtnActiveCash: {backgroundColor: COLORS.cashTab},
  toggleBtnActiveCredit: {backgroundColor: COLORS.creditTab},
  toggleBtnText: {fontSize: 15, fontWeight: '600', color: COLORS.subtext},
  toggleBtnTextActive: {color: '#fff'},

  // Input
  input: {
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 8,
    padding: 11,
    fontSize: 15,
    color: COLORS.text,
    marginBottom: 10,
  },
  phoneRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 0,
  },
  phoneSpinner: {marginLeft: 10, marginBottom: 10},
  row: {flexDirection: 'row', alignItems: 'flex-start'},
  spinner: {marginBottom: 10, marginLeft: 8},

  // Picker button (credit dropdown trigger)
  pickerBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 8,
    padding: 12,
    marginBottom: 10,
  },
  pickerBtnText: {fontSize: 15, color: COLORS.text, flex: 1},
  pickerBtnPlaceholder: {color: COLORS.subtext},
  pickerArrow: {color: COLORS.subtext, fontSize: 12},

  // Customer found badge
  customerFound: {
    backgroundColor: '#E8F5E9',
    borderRadius: 8,
    padding: 10,
    marginTop: 2,
  },
  customerFoundName: {fontSize: 15, fontWeight: '700', color: COLORS.success},
  customerFoundSub: {fontSize: 13, color: COLORS.success, marginTop: 1},
  customerFoundBalance: {fontSize: 13, color: COLORS.success, marginTop: 2},

  // IMEI dropdown
  dropdown: {
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 8,
    overflow: 'hidden',
  },
  dropdownItem: {
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  dropdownModel: {fontSize: 15, fontWeight: '600', color: COLORS.text},
  dropdownImei: {fontSize: 12, color: COLORS.subtext, marginTop: 2},
  dropdownPrice: {
    fontSize: 13,
    color: COLORS.primary,
    marginTop: 2,
    fontWeight: '600',
  },
  scanBtn: {
    marginLeft: 8,
    marginBottom: 10,
    backgroundColor: COLORS.primary,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scanBtnIcon: {
    fontSize: 18,
  },
  noResults: {
    fontSize: 13,
    color: COLORS.subtext,
    textAlign: 'center',
    marginTop: 8,
  },

  // Sale line items
  lineItem: {
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
    paddingBottom: 12,
    marginBottom: 12,
  },
  lineHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  lineModel: {fontSize: 15, fontWeight: '700', color: COLORS.text},
  lineRemove: {fontSize: 18, color: COLORS.danger, paddingHorizontal: 4},
  lineImei: {fontSize: 12, color: COLORS.subtext, marginTop: 2, marginBottom: 8},
  priceRow: {flexDirection: 'row', alignItems: 'center'},
  priceLabel: {fontSize: 14, color: COLORS.text, flex: 1},
  priceInput: {
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 7,
    fontSize: 15,
    color: COLORS.text,
    width: 120,
    textAlign: 'right',
  },
  belowCostWarn: {
    fontSize: 12,
    color: '#D97706',
    fontWeight: '600',
    marginTop: 5,
  },
  discountRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 4,
    marginBottom: 12,
  },
  discountLabel: {fontSize: 14, color: COLORS.subtext, flex: 1},
  totalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#E3F2FD',
    borderRadius: 8,
    padding: 12,
  },
  totalLabel: {fontSize: 16, fontWeight: 'bold', color: COLORS.primary},
  totalAmount: {fontSize: 18, fontWeight: 'bold', color: COLORS.primary},

  // Save button
  saveBtn: {
    backgroundColor: COLORS.primary,
    borderRadius: 10,
    padding: 16,
    alignItems: 'center',
    marginTop: 4,
  },
  saveBtnDisabled: {opacity: 0.5},
  saveBtnText: {color: '#fff', fontSize: 17, fontWeight: 'bold'},
  bottomPad: {height: 30},

  // Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modalSheet: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    maxHeight: '75%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  modalTitle: {fontSize: 17, fontWeight: 'bold', color: COLORS.text},
  modalClose: {fontSize: 20, color: COLORS.subtext, paddingHorizontal: 4},
  modalSearch: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  modalSearchInput: {
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 9,
    fontSize: 15,
    color: COLORS.text,
  },
  modalItem: {padding: 16},
  modalItemText: {fontSize: 16, color: COLORS.text},
  modalItemSub: {fontSize: 13, color: COLORS.subtext, marginTop: 3},
  separator: {height: 1, backgroundColor: COLORS.border, marginHorizontal: 16},
  emptyPicker: {padding: 30, alignItems: 'center'},
  emptyPickerText: {fontSize: 14, color: COLORS.subtext, textAlign: 'center'},
});
