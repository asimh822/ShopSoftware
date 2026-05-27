/**
 * NewPurchaseScreen — record a purchase on mobile.
 *
 * Flow A — Supplier Purchase (unchanged):
 *   1. Pick supplier
 *   2. Pick brand → model (pre-fills reference price)
 *   3. Enter IMEI + purchase price, add to list
 *   4. Save → POST /api/purchase  { purchase_type:"supplier", ... }
 *
 * Flow B — Cash Purchase (walk-in seller, no supplier):
 *   1. Enter eGadget reference number (mandatory)
 *   2. Select payment method: Cash / Bank Transfer / Split
 *   3. Pick brand → model, enter IMEIs (same as Flow A)
 *   4. Save → POST /api/purchase  { purchase_type:"cash", ... }
 *   5. Show success screen with PV#, eGadget ref, total, payment details
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
  const [brands,       setBrands]       = useState([]);
  const [suppliers,    setSuppliers]    = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [loading,      setLoading]      = useState(true);

  // ── Purchase type ──────────────────────────────────────────────────────────
  const [purchaseType, setPurchaseType] = useState('supplier'); // 'supplier' | 'cash'

  // ── Supplier mode ──────────────────────────────────────────────────────────
  const [selectedSupplier, setSelectedSupplier] = useState(null);

  // ── Cash purchase mode ─────────────────────────────────────────────────────
  const [egadgetRef,         setEgadgetRef]         = useState('');
  const [paymentMethod,      setPaymentMethod]      = useState('cash'); // 'cash'|'bank'|'split'
  const [selectedBankAcct,   setSelectedBankAcct]   = useState(null);
  const [bankRefInput,       setBankRefInput]       = useState('');
  const [cashAmountStr,      setCashAmountStr]      = useState('');
  const [bankAmountStr,      setBankAmountStr]      = useState('');

  // ── Shared (both modes) ────────────────────────────────────────────────────
  const [selectedBrand, setSelectedBrand] = useState(null);
  const [selectedModel, setSelectedModel] = useState(null);
  const [imeiInput,     setImeiInput]     = useState('');
  const [purchasePrice, setPurchasePrice] = useState('');
  const [lines,         setLines]         = useState([]);

  // ── UI state ───────────────────────────────────────────────────────────────
  // pickerModal: null | 'supplier' | 'brand' | 'model' | 'bank'
  const [pickerModal,  setPickerModal]  = useState(null);
  const [pickerSearch, setPickerSearch] = useState('');
  const [saving,       setSaving]       = useState(false);
  const [successData,  setSuccessData]  = useState(null); // set after cash purchase saved

  const today = todayDDMMYYYY();

  // ── Load master data ───────────────────────────────────────────────────────
  useEffect(() => { loadMasterData(); }, []);

  const loadMasterData = async () => {
    setLoading(true);
    try {
      const [bData, sData, baData] = await Promise.all([
        apiGet('/api/brands'),
        apiGet('/api/suppliers'),
        apiGet('/api/bank-account'),
      ]);
      setBrands(bData.brands || []);
      setSuppliers(sData.suppliers || []);
      setBankAccounts(baData.accounts || []);
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
    setPurchasePrice(String(Math.round(model.reference_price || 0)));
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

  // ── Save: Supplier purchase (existing flow — unchanged) ────────────────────
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

  // ── Save: Cash purchase ────────────────────────────────────────────────────
  const handleSaveCash = async () => {
    if (lines.length === 0) {
      Alert.alert('Empty', 'Add at least one phone.');
      return;
    }
    if (!egadgetRef.trim()) {
      Alert.alert('Required', 'eGadget Reference Number is required.');
      return;
    }
    if (paymentMethod === 'bank' && !selectedBankAcct) {
      Alert.alert('Required', 'Select a bank account for bank transfer.');
      return;
    }
    if (paymentMethod === 'split' && !selectedBankAcct) {
      Alert.alert('Required', 'Select a bank account for split payment.');
      return;
    }

    let cash_amount = 0;
    let bank_amount = 0;
    let bank_account_id = null;

    if (paymentMethod === 'cash') {
      cash_amount = total;
    } else if (paymentMethod === 'bank') {
      bank_amount    = total;
      bank_account_id = selectedBankAcct.id;
    } else {
      // split
      cash_amount    = parseFloat(cashAmountStr) || 0;
      bank_amount    = parseFloat(bankAmountStr) || 0;
      bank_account_id = selectedBankAcct.id;
      if (Math.abs((cash_amount + bank_amount) - total) > 1) {
        Alert.alert('Split Error',
          `Cash (PKR ${fmtPKR(cash_amount)}) + Bank (PKR ${fmtPKR(bank_amount)})\n` +
          `must equal total PKR ${fmtPKR(total)}.`);
        return;
      }
    }

    const salesman_id = await getSalesmanId();
    const payload = {
      purchase_type:  'cash',
      egadget_ref:    egadgetRef.trim(),
      date:           today,
      salesman_id:    parseInt(salesman_id),
      payment_method: paymentMethod,
      cash_amount,
      bank_amount,
      bank_account_id,
      bank_ref:       bankRefInput.trim(),
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
          pv_number:      data.pv_number,
          egadget_ref:    egadgetRef.trim(),
          total,
          payment_method: paymentMethod,
          cash_amount,
          bank_amount,
          bank_name:      selectedBankAcct ? selectedBankAcct.name : '',
          items:          lines.length,
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
      : pickerModal === 'bank'   ? bankAccounts
      : [];
    if (!pickerSearch.trim()) return raw;
    const q = pickerSearch.toLowerCase();
    return raw.filter(item => item.name.toLowerCase().includes(q));
  };

  // ── Success screen ─────────────────────────────────────────────────────────
  if (successData) {
    const pmLabel =
      successData.payment_method === 'cash'  ? 'Cash' :
      successData.payment_method === 'bank'  ? `Bank Transfer — ${successData.bank_name}` :
      `Split  (Cash PKR ${fmtPKR(successData.cash_amount)} / Bank PKR ${fmtPKR(successData.bank_amount)})`;

    return (
      <View style={s.successWrap}>
        <View style={s.successIcon}>
          <Text style={s.successIconText}>✓</Text>
        </View>
        <Text style={s.successTitle}>Cash Purchase Saved</Text>
        <View style={s.successCard}>
          <SuccessRow label="PV Number"       value={successData.pv_number} />
          <SuccessRow label="eGadget Ref"     value={successData.egadget_ref} />
          <SuccessRow label="Items Purchased" value={`${successData.items} phone(s)`} />
          <SuccessRow label="Total Amount"    value={`PKR ${fmtPKR(successData.total)}`} bold />
          <SuccessRow label="Payment"         value={pmLabel} />
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
  const splitCash = parseFloat(cashAmountStr) || 0;
  const splitBank = parseFloat(bankAmountStr) || 0;
  const splitOk   = total > 0 && Math.abs((splitCash + splitBank) - total) <= 1;

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

          {/* ── Supplier Card (supplier mode) ───────────────────────────── */}
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

          {/* ── Cash Purchase Card (cash mode) ─────────────────────────── */}
          {purchaseType === 'cash' && (
            <View style={s.card}>
              <Text style={s.sectionTitle}>Cash Purchase Details</Text>

              {/* eGadget Reference */}
              <Text style={s.fieldLbl}>eGadget Reference # *</Text>
              <TextInput
                style={[s.input, {marginBottom: 16}]}
                placeholder="Mandatory — eGadget reference number"
                placeholderTextColor={C.subtext}
                value={egadgetRef}
                onChangeText={setEgadgetRef}
                autoCapitalize="characters"
                autoCorrect={false}
              />

              {/* Payment Method Toggle */}
              <Text style={s.fieldLbl}>Payment Method *</Text>
              <View style={s.payRow}>
                {/* Cash */}
                <TouchableOpacity
                  style={[s.payBtn, s.payBtnLeft,
                          paymentMethod === 'cash' && s.payBtnActive]}
                  onPress={() => setPaymentMethod('cash')}>
                  <Text style={[s.payBtnTxt,
                                paymentMethod === 'cash' && s.payBtnTxtActive]}>
                    Cash
                  </Text>
                </TouchableOpacity>
                {/* Bank */}
                <TouchableOpacity
                  style={[s.payBtn, s.payBtnMid,
                          paymentMethod === 'bank' && s.payBtnActive]}
                  onPress={() => setPaymentMethod('bank')}>
                  <Text style={[s.payBtnTxt,
                                paymentMethod === 'bank' && s.payBtnTxtActive]}>
                    Bank
                  </Text>
                </TouchableOpacity>
                {/* Split */}
                <TouchableOpacity
                  style={[s.payBtn, s.payBtnRight,
                          paymentMethod === 'split' && s.payBtnActive]}
                  onPress={() => setPaymentMethod('split')}>
                  <Text style={[s.payBtnTxt,
                                paymentMethod === 'split' && s.payBtnTxtActive]}>
                    Split
                  </Text>
                </TouchableOpacity>
              </View>

              {/* Bank Transfer details */}
              {paymentMethod === 'bank' && (
                <View style={s.payDetail}>
                  <Text style={s.fieldLbl}>Bank Account *</Text>
                  <TouchableOpacity
                    style={s.pickerBtn}
                    onPress={() => { setPickerSearch(''); setPickerModal('bank'); }}>
                    <Text style={[s.pickerTxt,
                                  !selectedBankAcct && s.pickerPlaceholder]}>
                      {selectedBankAcct ? selectedBankAcct.name : 'Select Bank Account...'}
                    </Text>
                    <Text style={s.pickerArrow}>▼</Text>
                  </TouchableOpacity>
                  <Text style={[s.fieldLbl, {marginTop: 12}]}>Bank Reference</Text>
                  <TextInput
                    style={s.input}
                    placeholder="Transfer reference number (optional)"
                    placeholderTextColor={C.subtext}
                    value={bankRefInput}
                    onChangeText={setBankRefInput}
                    autoCapitalize="none"
                    autoCorrect={false}
                  />
                </View>
              )}

              {/* Split details */}
              {paymentMethod === 'split' && (
                <View style={s.payDetail}>
                  <View style={s.splitAmtRow}>
                    <View style={s.splitField}>
                      <Text style={s.fieldLbl}>Cash Amount (PKR) *</Text>
                      <TextInput
                        style={s.input}
                        placeholder="0"
                        placeholderTextColor={C.subtext}
                        value={cashAmountStr}
                        onChangeText={setCashAmountStr}
                        keyboardType="number-pad"
                      />
                    </View>
                    <View style={[s.splitField, {marginLeft: 10}]}>
                      <Text style={s.fieldLbl}>Bank Amount (PKR) *</Text>
                      <TextInput
                        style={s.input}
                        placeholder="0"
                        placeholderTextColor={C.subtext}
                        value={bankAmountStr}
                        onChangeText={setBankAmountStr}
                        keyboardType="number-pad"
                      />
                    </View>
                  </View>
                  {total > 0 && (
                    <Text style={[s.splitHint,
                                  splitOk ? s.splitHintOk : s.splitHintErr]}>
                      {splitOk
                        ? `✓ Total matches: PKR ${fmtPKR(total)}`
                        : `Must equal PKR ${fmtPKR(total)}  (currently PKR ${fmtPKR(splitCash + splitBank)})`}
                    </Text>
                  )}
                  <Text style={[s.fieldLbl, {marginTop: 8}]}>Bank Account *</Text>
                  <TouchableOpacity
                    style={s.pickerBtn}
                    onPress={() => { setPickerSearch(''); setPickerModal('bank'); }}>
                    <Text style={[s.pickerTxt,
                                  !selectedBankAcct && s.pickerPlaceholder]}>
                      {selectedBankAcct ? selectedBankAcct.name : 'Select Bank Account...'}
                    </Text>
                    <Text style={s.pickerArrow}>▼</Text>
                  </TouchableOpacity>
                  <Text style={[s.fieldLbl, {marginTop: 12}]}>Bank Reference</Text>
                  <TextInput
                    style={s.input}
                    placeholder="Bank transfer reference (optional)"
                    placeholderTextColor={C.subtext}
                    value={bankRefInput}
                    onChangeText={setBankRefInput}
                    autoCapitalize="none"
                    autoCorrect={false}
                  />
                </View>
              )}
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
              <TextInput
                style={s.input}
                placeholder="IMEI (exactly 15 digits)"
                placeholderTextColor={C.subtext}
                value={imeiInput}
                onChangeText={setImeiInput}
                keyboardType="number-pad"
                maxLength={15}
              />
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
                : pickerModal === 'model'   ? 'Select Model'
                :                            'Select Bank Account'}
              </Text>
              <TouchableOpacity onPress={() => setPickerModal(null)}>
                <Text style={s.modalClose}>✕</Text>
              </TouchableOpacity>
            </View>

            {/* Search (not needed for short bank list) */}
            {pickerModal !== 'bank' && (
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
            )}

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
                    } else if (pickerModal === 'model') {
                      handleSelectModel(item);
                    } else {
                      // bank
                      setSelectedBankAcct(item);
                      setPickerModal(null);
                    }
                  }}>
                  <Text style={s.modalItemTxt}>{item.name}</Text>
                  {pickerModal === 'model' && (
                    <Text style={s.modalItemSub}>
                      Ref: PKR {fmtPKR(item.reference_price)}
                    </Text>
                  )}
                </TouchableOpacity>
              )}
              ItemSeparatorComponent={() => <View style={s.sep} />}
              keyboardShouldPersistTaps="handled"
              ListEmptyComponent={
                <Text style={s.emptyTxt}>
                  {pickerModal === 'bank'
                    ? 'No bank accounts found. Add accounts in desktop Settings.'
                    : 'No results found.'}
                </Text>
              }
            />
          </View>
        </View>
      </Modal>
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

  // ── Payment method toggle ─────────────────────────────────────────────────
  payRow: {flexDirection: 'row', marginBottom: 14},
  payBtn: {
    flex: 1,
    paddingVertical: 9,
    alignItems: 'center',
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: C.toggleBdr,
    backgroundColor: C.toggle,
  },
  payBtnLeft:    {borderLeftWidth: 1, borderRightWidth: 0, borderTopLeftRadius: 7, borderBottomLeftRadius: 7},
  payBtnMid:     {borderLeftWidth: 1, borderRightWidth: 0},
  payBtnRight:   {borderLeftWidth: 1, borderRightWidth: 1, borderTopRightRadius: 7, borderBottomRightRadius: 7},
  payBtnActive:  {backgroundColor: C.blue, borderColor: C.blue},
  payBtnTxt:     {fontSize: 14, fontWeight: '600', color: C.toggleTxt},
  payBtnTxtActive: {color: '#FFFFFF'},

  // ── Payment detail area ───────────────────────────────────────────────────
  payDetail:    {marginTop: 4},
  splitAmtRow:  {flexDirection: 'row'},
  splitField:   {flex: 1},
  splitHint:    {fontSize: 13, marginBottom: 10, textAlign: 'center', fontWeight: '500'},
  splitHintOk:  {color: C.primary},
  splitHintErr: {color: C.danger},

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
  modalOverlay:    {flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end'},
  modalSheet:      {backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, maxHeight: '70%'},
  modalHeader:     {flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16, borderBottomWidth: 1, borderBottomColor: C.border},
  modalTitle:      {fontSize: 17, fontWeight: 'bold', color: C.text},
  modalClose:      {fontSize: 20, color: C.subtext, paddingHorizontal: 4},
  modalSearch:     {paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border},
  modalSearchInput:{borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 9, fontSize: 15, color: C.text},
  modalItem:       {padding: 16},
  modalItemTxt:    {fontSize: 16, color: C.text},
  modalItemSub:    {fontSize: 13, color: C.subtext, marginTop: 3},
  sep:             {height: 1, backgroundColor: C.border, marginHorizontal: 16},
  emptyTxt:        {padding: 24, textAlign: 'center', color: C.subtext, fontSize: 14},

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
