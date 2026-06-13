/**
 * NewPurchaseScreen — record a purchase on mobile.
 *
 * Flow A — Supplier Purchase (credit — goes to supplier ledger):
 *   1. Pick supplier
 *   2. Pick brand → model (pre-fills reference price)
 *   3. Enter IMEI + purchase price, add to list
 *   4. Save → POST /api/purchase  { purchase_type:"supplier", ... }
 *   No cash changes hands — recorded as a payable to the supplier.
 *
 * Flow B — Cash Purchase (walk-in seller, no supplier):
 *   1. Pick brand → model, enter IMEIs
 *   2. Enter eGadget reference number (optional)
 *   3. Save → POST /api/purchase  { purchase_type:"cash", payment_method:"cash", ... }
 *   Always paid in full by cash — no bank or split options.
 */

import React, {useState, useEffect} from 'react';
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
  Modal,
  FlatList,
} from 'react-native';
import {apiGet, apiPost, getSalesmanId} from '../config/api';
import {fmtPKR, todayDDMMYYYY} from '../utils/formatting';
import BarcodeScanner, {requestCameraPermission} from '../components/BarcodeScanner';

const C = {
  primary:   '#2E7D32',
  bg:        '#F5F5F5',
  card:      '#FFFFFF',
  border:    '#E0E0E0',
  text:      '#212121',
  subtext:   '#757575',
  danger:    '#C62828',
  blue:      '#1565C0',
  blueLight: '#E3F2FD',
  toggle:    '#F1F5F9',
  toggleBdr: '#CBD5E1',
  toggleTxt: '#64748B',
};

// ── Tiny helper to render a success detail row ────────────────────────────────
function SuccessRow({label, value, bold}) {
  return (
    <View style={sr.row}>
      <Text style={sr.label}>{label}</Text>
      <Text style={[sr.value, bold && sr.bold]}>{value}</Text>
    </View>
  );
}

const sr = StyleSheet.create({
  row:   {flexDirection:'row', justifyContent:'space-between', paddingVertical:10,
           borderBottomWidth:1, borderBottomColor:C.border},
  label: {fontSize:14, color:C.subtext, flex:1},
  value: {fontSize:14, color:C.text, flex:2, textAlign:'right'},
  bold:  {fontWeight:'bold', color:C.primary, fontSize:16},
});

// ── Main component ────────────────────────────────────────────────────────────
export default function NewPurchaseScreen({navigation}) {
  // ── Master data ────────────────────────────────────────────────────────────
  const [brands,    setBrands]    = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [loading,   setLoading]   = useState(true);

  // ── Purchase type ──────────────────────────────────────────────────────────
  const [purchaseType, setPurchaseType] = useState('supplier'); // 'supplier' | 'cash'

  // ── Supplier mode ──────────────────────────────────────────────────────────
  const [selectedSupplier, setSelectedSupplier] = useState(null);

  // ── Cash purchase mode ─────────────────────────────────────────────────────
  const [egadgetRef, setEgadgetRef] = useState('');

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
    setImeiInput(digits);   // fills the IMEI field; user reviews then taps Add
  };

  // ── Shared (both modes) ────────────────────────────────────────────────────
  const [selectedBrand, setSelectedBrand] = useState(null);
  const [selectedModel, setSelectedModel] = useState(null);
  const [imeiInput,     setImeiInput]     = useState('');
  const [purchasePrice, setPurchasePrice] = useState('');
  const [lines,         setLines]         = useState([]);

  // ── UI state ───────────────────────────────────────────────────────────────
  // pickerModal: null | 'supplier' | 'brand' | 'model'
  const [pickerModal,  setPickerModal]  = useState(null);
  const [pickerSearch, setPickerSearch] = useState('');
  const [saving,       setSaving]       = useState(false);
  const [successData,  setSuccessData]  = useState(null);

  const today = todayDDMMYYYY();

  // ── Load master data ───────────────────────────────────────────────────────
  useEffect(() => { loadMasterData(); }, []);

  const loadMasterData = async () => {
    setLoading(true);
    try {
      const [bData, sData] = await Promise.all([
        apiGet('/api/brands'),
        apiGet('/api/suppliers'),
      ]);
      setBrands(bData.brands || []);
      setSuppliers(sData.suppliers || []);
    } catch (err) {
      if (err.message === 'SESSION_EXPIRED') navigation.replace('Login');
      else Alert.alert('Error', 'Failed to load data. Check connection.');
    } finally {
      setLoading(false);
    }
  };

  // ── Brand / model selection ────────────────────────────────────────────────
  const handleSelectBrand = brand => {
    setSelectedBrand(brand);
    setSelectedModel(null);
    setPurchasePrice('');
    setPickerModal(null);
  };

  const handleSelectModel = model => {
    setSelectedModel(model);
    setPurchasePrice(model.reference_price != null ? String(Math.round(model.reference_price)) : '');
    setPickerModal(null);
  };

  // ── Add IMEI line ──────────────────────────────────────────────────────────
  const handleAddLine = () => {
    const imei = imeiInput.trim();
    if (!selectedModel) {
      Alert.alert('Required', 'Select a brand and model first.');
      return;
    }
    if (imei.length !== 15 || !/^\d+$/.test(imei)) {
      Alert.alert('Invalid IMEI', 'IMEI must be exactly 15 digits.');
      return;
    }
    const price = parseFloat(purchasePrice);
    if (!price || price <= 0) {
      Alert.alert('Invalid Price', 'Enter a valid purchase price.');
      return;
    }
    if (lines.some(l => l.imei === imei)) {
      Alert.alert('Duplicate', 'This IMEI is already in the list.');
      return;
    }
    setLines(prev => [...prev, {
      imei,
      model_id:       selectedModel.id,
      model:          selectedModel.name,
      brand:          selectedBrand.name,
      purchase_price: price,
    }]);
    setImeiInput('');
  };

  const removeLine = imei => setLines(prev => prev.filter(l => l.imei !== imei));

  const total = lines.reduce((s, l) => s + l.purchase_price, 0);

  // ── Save: Supplier purchase (credit — no cash changes hands) ──────────────
  const handleSaveSupplier = async () => {
    if (!selectedSupplier) {
      Alert.alert('Required', 'Select a supplier.');
      return;
    }
    if (lines.length === 0) {
      Alert.alert('Empty', 'Add at least one phone.');
      return;
    }
    const salesman_id = await getSalesmanId();
    const payload = {
      purchase_type: 'supplier',
      supplier_id:   selectedSupplier.id,
      date:          today,
      salesman_id:   parseInt(salesman_id),
      lines:         lines.map(l => ({
        imei:           l.imei,
        model_id:       l.model_id,
        purchase_price: l.purchase_price,
      })),
    };
    setSaving(true);
    try {
      const data = await apiPost('/api/purchase', payload);
      if (data.success) {
        Alert.alert(
          'Purchase Saved',
          `PV ${data.pv_number} created.\n${lines.length} phone(s) added to stock.`,
          [{text: 'OK', onPress: () => navigation.goBack()}],
        );
      } else {
        Alert.alert('Error', data.error || 'Purchase failed.');
      }
    } catch (err) {
      if (err.message === 'SESSION_EXPIRED') navigation.replace('Login');
      else Alert.alert('Error', err.message || 'Purchase failed.');
    } finally {
      setSaving(false);
    }
  };

  // ── Save: Cash purchase (always paid in full by cash) ─────────────────────
  const handleSaveCash = async () => {
    if (lines.length === 0) {
      Alert.alert('Empty', 'Add at least one phone.');
      return;
    }

    const salesman_id = await getSalesmanId();
    const payload = {
      purchase_type:  'cash',
      egadget_ref:    egadgetRef.trim(),
      date:           today,
      salesman_id:    parseInt(salesman_id),
      payment_method: 'cash',
      cash_amount:    total,
      bank_amount:    0,
      bank_account_id: null,
      bank_ref:       '',
      lines:          lines.map(l => ({
        imei:           l.imei,
        model_id:       l.model_id,
        purchase_price: l.purchase_price,
      })),
    };

    setSaving(true);
    try {
      const data = await apiPost('/api/purchase', payload);
      if (data.success) {
        setSuccessData({
          pv_number:   data.pv_number,
          egadget_ref: egadgetRef.trim(),
          total,
          items:       lines.length,
        });
      } else {
        Alert.alert('Error', data.error || 'Purchase failed.');
      }
    } catch (err) {
      if (err.message === 'SESSION_EXPIRED') navigation.replace('Login');
      else Alert.alert('Error', err.message || 'Purchase failed.');
    } finally {
      setSaving(false);
    }
  };

  const handleSave = () =>
    purchaseType === 'supplier' ? handleSaveSupplier() : handleSaveCash();

  // ── Picker data ────────────────────────────────────────────────────────────
  const currentModels = selectedBrand ? selectedBrand.models || [] : [];

  const getFilteredPickerData = () => {
    const raw =
      pickerModal === 'supplier' ? suppliers
      : pickerModal === 'brand'  ? brands
      : pickerModal === 'model'  ? currentModels
      : [];
    if (!pickerSearch.trim()) return raw;
    const q = pickerSearch.toLowerCase();
    return raw.filter(item => item.name.toLowerCase().includes(q));
  };

  // ── Success screen ─────────────────────────────────────────────────────────
  if (successData) {
    return (
      <View style={s.successWrap}>
        <View style={s.successIcon}>
          <Text style={s.successIconText}>✓</Text>
        </View>
        <Text style={s.successTitle}>Cash Purchase Saved</Text>
        <View style={s.successCard}>
          <SuccessRow label="PV Number"       value={successData.pv_number} />
          {!!successData.egadget_ref && (
            <SuccessRow label="eGadget Ref" value={successData.egadget_ref} />
          )}
          <SuccessRow label="Items Purchased" value={`${successData.items} phone(s)`} />
          <SuccessRow label="Total Amount"    value={`PKR ${fmtPKR(successData.total)}`} bold />
          <SuccessRow label="Payment"         value="Cash" />
        </View>
        <TouchableOpacity style={s.successDoneBtn} onPress={() => navigation.goBack()}>
          <Text style={s.successDoneTxt}>Done</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ── Loading ────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <View style={s.center}>
        <ActivityIndicator size="large" color={C.primary} />
        <Text style={s.loadingTxt}>Loading...</Text>
      </View>
    );
  }

  // ── Form ───────────────────────────────────────────────────────────────────
  return (
    <>
      <KeyboardAvoidingView
        style={s.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          style={s.scroll}
          contentContainerStyle={s.content}
          keyboardShouldPersistTaps="handled">

          {/* ── Purchase Type Toggle ────────────────────────────────────── */}
          <View style={s.toggleRow}>
            <TouchableOpacity
              style={[s.toggleBtn, s.toggleLeft,
                      purchaseType === 'supplier' && s.toggleActive]}
              onPress={() => setPurchaseType('supplier')}>
              <Text style={[s.toggleTxt,
                            purchaseType === 'supplier' && s.toggleTxtActive]}>
                Supplier
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[s.toggleBtn, s.toggleRight,
                      purchaseType === 'cash' && s.toggleActive]}
              onPress={() => setPurchaseType('cash')}>
              <Text style={[s.toggleTxt,
                            purchaseType === 'cash' && s.toggleTxtActive]}>
                Cash Purchase
              </Text>
            </TouchableOpacity>
          </View>

          {/* ── Supplier Card (supplier mode only) ──────────────────────── */}
          {purchaseType === 'supplier' && (
            <View style={s.card}>
              <Text style={s.sectionTitle}>Supplier</Text>
              <TouchableOpacity
                style={s.pickerBtn}
                onPress={() => { setPickerSearch(''); setPickerModal('supplier'); }}>
                <Text style={[s.pickerTxt,
                              !selectedSupplier && s.pickerPlaceholder]}>
                  {selectedSupplier ? selectedSupplier.name : 'Select Supplier...'}
                </Text>
                <Text style={s.pickerArrow}>▼</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* ── Brand + Model (shared) ──────────────────────────────────── */}
          <View style={s.card}>
            <Text style={s.sectionTitle}>Phone Model</Text>
            <TouchableOpacity
              style={s.pickerBtn}
              onPress={() => { setPickerSearch(''); setPickerModal('brand'); }}>
              <Text style={[s.pickerTxt, !selectedBrand && s.pickerPlaceholder]}>
                {selectedBrand ? selectedBrand.name : 'Select Brand...'}
              </Text>
              <Text style={s.pickerArrow}>▼</Text>
            </TouchableOpacity>

            {selectedBrand && (
              <TouchableOpacity
                style={[s.pickerBtn, {marginTop: 10}]}
                onPress={() => { setPickerSearch(''); setPickerModal('model'); }}>
                <Text style={[s.pickerTxt, !selectedModel && s.pickerPlaceholder]}>
                  {selectedModel ? selectedModel.name : 'Select Model...'}
                </Text>
                <Text style={s.pickerArrow}>▼</Text>
              </TouchableOpacity>
            )}
          </View>

          {/* ── IMEI Entry (shared) ─────────────────────────────────────── */}
          {selectedModel && (
            <View style={s.card}>
              <Text style={s.sectionTitle}>Add IMEI</Text>
              <View style={s.imeiRow}>
                <TextInput
                  style={[s.input, s.imeiInput]}
                  placeholder="IMEI (exactly 15 digits)"
                  placeholderTextColor={C.subtext}
                  value={imeiInput}
                  onChangeText={setImeiInput}
                  keyboardType="number-pad"
                  maxLength={15}
                />
                <TouchableOpacity style={s.scanBtn} onPress={openScanner}>
                  <Text style={s.scanBtnIcon}>📷</Text>
                </TouchableOpacity>
              </View>
              <View style={s.priceRow}>
                <Text style={s.priceLbl}>Purchase Price (PKR):</Text>
                <TextInput
                  style={s.priceInput}
                  value={purchasePrice}
                  onChangeText={setPurchasePrice}
                  keyboardType="number-pad"
                />
              </View>
              <TouchableOpacity style={s.addBtn} onPress={handleAddLine}>
                <Text style={s.addBtnTxt}>+ Add to List</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* ── Lines List (shared) ─────────────────────────────────────── */}
          {lines.length > 0 && (
            <View style={s.card}>
              <Text style={s.sectionTitle}>
                Purchase Items ({lines.length})
              </Text>
              {lines.map(line => (
                <View key={line.imei} style={s.lineItem}>
                  <View style={s.lineRow}>
                    <View style={s.flex}>
                      <Text style={s.lineModel}>
                        {line.brand} {line.model}
                      </Text>
                      <Text style={s.lineImei}>{line.imei}</Text>
                    </View>
                    <View style={s.lineRight}>
                      <Text style={s.linePrice}>
                        PKR {fmtPKR(line.purchase_price)}
                      </Text>
                      <TouchableOpacity onPress={() => removeLine(line.imei)}>
                        <Text style={s.lineRemove}>✕</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                </View>
              ))}
              <View style={s.totalRow}>
                <Text style={s.totalLbl}>TOTAL</Text>
                <Text style={s.totalAmt}>PKR {fmtPKR(total)}</Text>
              </View>
            </View>
          )}

          {/* ── Cash Purchase Details (cash mode — eGadget ref only) ─────── */}
          {purchaseType === 'cash' && (
            <View style={s.card}>
              <Text style={s.sectionTitle}>Cash Purchase Details</Text>
              <Text style={s.fieldLbl}>eGadget Reference #</Text>
              <TextInput
                style={[s.input, {marginBottom: 4}]}
                placeholder="Optional — eGadget reference number"
                placeholderTextColor={C.subtext}
                value={egadgetRef}
                onChangeText={setEgadgetRef}
                autoCapitalize="characters"
                autoCorrect={false}
              />
            </View>
          )}

          {/* ── Save Button ─────────────────────────────────────────────── */}
          <TouchableOpacity
            style={[s.saveBtn, saving && s.saveBtnOff]}
            onPress={handleSave}
            disabled={saving}>
            {saving ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={s.saveBtnTxt}>
                {purchaseType === 'cash' ? 'Save Cash Purchase' : 'Save Purchase'}
              </Text>
            )}
          </TouchableOpacity>

          <View style={s.bottomPad} />
        </ScrollView>
      </KeyboardAvoidingView>

      {/* ── Picker Modal ────────────────────────────────────────────────── */}
      <Modal
        visible={pickerModal !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setPickerModal(null)}>
        <View style={s.modalOverlay}>
          <View style={s.modalSheet}>
            <View style={s.modalHeader}>
              <Text style={s.modalTitle}>
                {pickerModal === 'supplier' ? 'Select Supplier'
                : pickerModal === 'brand'   ? 'Select Brand'
                :                            'Select Model'}
              </Text>
              <TouchableOpacity onPress={() => setPickerModal(null)}>
                <Text style={s.modalClose}>✕</Text>
              </TouchableOpacity>
            </View>

            {/* Search bar */}
            <View style={s.modalSearch}>
              <TextInput
                style={s.modalSearchInput}
                placeholder={
                  pickerModal === 'supplier' ? 'Search supplier...'
                  : pickerModal === 'brand'  ? 'Search brand...'
                  :                           'Search model...'}
                placeholderTextColor={C.subtext}
                value={pickerSearch}
                onChangeText={setPickerSearch}
                autoCapitalize="none"
              />
            </View>

            <FlatList
              data={getFilteredPickerData()}
              keyExtractor={item => String(item.id)}
              renderItem={({item}) => (
                <TouchableOpacity
                  style={s.modalItem}
                  onPress={() => {
                    if (pickerModal === 'supplier') {
                      setSelectedSupplier(item);
                      setPickerModal(null);
                    } else if (pickerModal === 'brand') {
                      handleSelectBrand(item);
                    } else {
                      handleSelectModel(item);
                    }
                  }}>
                  <Text style={s.modalItemTxt}>{item.name}</Text>
                  {pickerModal === 'model' && item.reference_price != null && (
                    <Text style={s.modalItemSub}>
                      Ref: PKR {fmtPKR(item.reference_price)}
                    </Text>
                  )}
                </TouchableOpacity>
              )}
              ItemSeparatorComponent={() => <View style={s.sep} />}
              keyboardShouldPersistTaps="handled"
              ListEmptyComponent={
                <Text style={s.emptyTxt}>No results found.</Text>
              }
            />
          </View>
        </View>
      </Modal>

      {/* Barcode / IMEI scanner */}
      <BarcodeScanner
        visible={scannerVisible}
        onScanned={handleScanned}
        onClose={() => setScannerVisible(false)}
      />
    </>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────────
const s = StyleSheet.create({
  flex:        {flex: 1},
  center:      {flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: C.bg},
  loadingTxt:  {marginTop: 12, color: C.subtext},
  scroll:      {flex: 1, backgroundColor: C.bg},
  content:     {padding: 16},

  // ── Purchase type toggle ──────────────────────────────────────────────────
  toggleRow: {
    flexDirection: 'row',
    marginBottom: 12,
    borderRadius: 8,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: C.toggleBdr,
  },
  toggleBtn: {
    flex: 1,
    paddingVertical: 11,
    alignItems: 'center',
    backgroundColor: C.toggle,
  },
  toggleLeft:      {borderRightWidth: 1, borderRightColor: C.toggleBdr},
  toggleRight:     {},
  toggleActive:    {backgroundColor: C.primary},
  toggleTxt:       {fontSize: 14, fontWeight: '600', color: C.toggleTxt},
  toggleTxtActive: {color: '#FFFFFF'},

  // ── Card ──────────────────────────────────────────────────────────────────
  card: {
    backgroundColor: C.card,
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
    fontSize: 13,
    fontWeight: '700',
    color: C.subtext,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 12,
  },
  fieldLbl: {fontSize: 13, fontWeight: '600', color: '#424242', marginBottom: 6},

  // ── Picker button ─────────────────────────────────────────────────────────
  pickerBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: C.border,
    borderRadius: 8,
    padding: 12,
  },
  pickerTxt:         {fontSize: 15, color: C.text, flex: 1},
  pickerPlaceholder: {color: C.subtext},
  pickerArrow:       {color: C.subtext, fontSize: 12},

  // ── Inputs ────────────────────────────────────────────────────────────────
  input: {
    borderWidth: 1,
    borderColor: C.border,
    borderRadius: 8,
    padding: 11,
    fontSize: 15,
    color: C.text,
    marginBottom: 10,
  },
  imeiRow:    {flexDirection: 'row', alignItems: 'center', marginBottom: 0},
  imeiInput:  {flex: 1, marginBottom: 10},
  scanBtn:    {
    marginLeft: 8,
    marginBottom: 10,
    backgroundColor: C.primary,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scanBtnIcon: {fontSize: 18},
  priceRow:   {flexDirection: 'row', alignItems: 'center', marginBottom: 12},
  priceLbl:   {fontSize: 14, color: C.text, flex: 1},
  priceInput: {
    borderWidth: 1,
    borderColor: C.border,
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 7,
    fontSize: 15,
    color: C.text,
    width: 120,
    textAlign: 'right',
  },

  // ── Add line button ───────────────────────────────────────────────────────
  addBtn:    {backgroundColor: C.primary, borderRadius: 8, padding: 12, alignItems: 'center'},
  addBtnTxt: {color: '#fff', fontWeight: 'bold', fontSize: 15},

  // ── Lines list ────────────────────────────────────────────────────────────
  lineItem:   {paddingBottom: 12, marginBottom: 12, borderBottomWidth: 1, borderBottomColor: C.border},
  lineRow:    {flexDirection: 'row', alignItems: 'flex-start'},
  lineModel:  {fontSize: 14, fontWeight: '700', color: C.text},
  lineImei:   {fontSize: 12, color: C.subtext, marginTop: 2},
  lineRight:  {alignItems: 'flex-end', marginLeft: 8},
  linePrice:  {fontSize: 14, fontWeight: '600', color: C.primary},
  lineRemove: {fontSize: 18, color: C.danger, marginTop: 4},
  totalRow:   {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: '#E8F5E9',
    borderRadius: 8,
    padding: 12,
    marginTop: 4,
  },
  totalLbl: {fontSize: 16, fontWeight: 'bold', color: C.primary},
  totalAmt: {fontSize: 18, fontWeight: 'bold', color: C.primary},

  // ── Save button ───────────────────────────────────────────────────────────
  saveBtn:    {backgroundColor: C.primary, borderRadius: 10, padding: 16, alignItems: 'center'},
  saveBtnOff: {opacity: 0.5},
  saveBtnTxt: {color: '#fff', fontSize: 17, fontWeight: 'bold'},
  bottomPad:  {height: 30},

  // ── Picker modal ──────────────────────────────────────────────────────────
  modalOverlay:     {flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end'},
  modalSheet:       {backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, maxHeight: '70%'},
  modalHeader:      {flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16, borderBottomWidth: 1, borderBottomColor: C.border},
  modalTitle:       {fontSize: 17, fontWeight: 'bold', color: C.text},
  modalClose:       {fontSize: 20, color: C.subtext, paddingHorizontal: 4},
  modalSearch:      {paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border},
  modalSearchInput: {borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 9, fontSize: 15, color: C.text},
  modalItem:        {padding: 16},
  modalItemTxt:     {fontSize: 16, color: C.text},
  modalItemSub:     {fontSize: 13, color: C.subtext, marginTop: 3},
  sep:              {height: 1, backgroundColor: C.border, marginHorizontal: 16},
  emptyTxt:         {padding: 24, textAlign: 'center', color: C.subtext, fontSize: 14},

  // ── Success screen ────────────────────────────────────────────────────────
  successWrap:    {flex: 1, backgroundColor: C.bg, padding: 24, alignItems: 'center', justifyContent: 'center'},
  successIcon:    {width: 80, height: 80, borderRadius: 40, backgroundColor: C.primary, justifyContent: 'center', alignItems: 'center', marginBottom: 16},
  successIconText:{color: '#fff', fontSize: 40, fontWeight: 'bold'},
  successTitle:   {fontSize: 22, fontWeight: 'bold', color: C.text, marginBottom: 24},
  successCard:    {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    width: '100%',
    elevation: 2,
    shadowColor: '#000',
    shadowOpacity: 0.08,
    shadowRadius: 4,
    shadowOffset: {width: 0, height: 2},
    marginBottom: 28,
  },
  successDoneBtn: {backgroundColor: C.primary, borderRadius: 10, paddingVertical: 14, paddingHorizontal: 60},
  successDoneTxt: {color: '#fff', fontSize: 17, fontWeight: 'bold'},
});
