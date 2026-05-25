/**
 * NewPurchaseScreen — record a purchase on mobile.
 *
 * Flow:
 *  1. Pick supplier
 *  2. Pick brand → model (pre-fills reference price)
 *  3. Enter IMEI + purchase price, add to list (duplicate check)
 *  4. Save → POST /api/purchase
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

const COLORS = {
  primary: '#2E7D32',
  bg: '#F5F5F5',
  card: '#FFFFFF',
  border: '#E0E0E0',
  text: '#212121',
  subtext: '#757575',
  danger: '#C62828',
};

export default function NewPurchaseScreen({navigation}) {
  const [brands, setBrands] = useState([]); // [{id, name, models:[{id, name, reference_price}]}]
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);

  const [selectedSupplier, setSelectedSupplier] = useState(null);
  const [selectedBrand, setSelectedBrand] = useState(null);
  const [selectedModel, setSelectedModel] = useState(null);

  const [imeiInput, setImeiInput] = useState('');
  const [purchasePrice, setPurchasePrice] = useState('');
  const [lines, setLines] = useState([]); // [{imei, model_id, model, brand, purchase_price}]

  const [pickerModal, setPickerModal] = useState(null); // null | 'supplier' | 'brand' | 'model'
  const [pickerSearch, setPickerSearch] = useState('');
  const [saving, setSaving] = useState(false);

  const today = todayDDMMYYYY();

  useEffect(() => {
    loadMasterData();
  }, []);

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

  const handleSelectBrand = (brand) => {
    setSelectedBrand(brand);
    setSelectedModel(null);
    setPurchasePrice('');
    setPickerModal(null);
  };

  const handleSelectModel = (model) => {
    setSelectedModel(model);
    setPurchasePrice(String(Math.round(model.reference_price)));
    setPickerModal(null);
  };

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
    // Duplicate check
    if (lines.some(l => l.imei === imei)) {
      Alert.alert('Duplicate', 'This IMEI is already in the list.');
      return;
    }

    setLines(prev => [
      ...prev,
      {
        imei,
        model_id: selectedModel.id,
        model: selectedModel.name,
        brand: selectedBrand.name,
        purchase_price: price,
      },
    ]);
    setImeiInput('');
    // Keep price/model for next entry
  };

  const removeLine = (imei) => {
    setLines(prev => prev.filter(l => l.imei !== imei));
  };

  const handleSave = async () => {
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
      supplier_id: selectedSupplier.id,
      date: today,
      salesman_id: parseInt(salesman_id),
      lines: lines.map(l => ({
        imei: l.imei,
        model_id: l.model_id,
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

  const total = lines.reduce((s, l) => s + l.purchase_price, 0);

  // Filtered list for the active picker modal
  const getFilteredPickerData = () => {
    const raw =
      pickerModal === 'supplier'
        ? suppliers
        : pickerModal === 'brand'
        ? brands
        : currentModels;
    if (!pickerSearch.trim()) return raw;
    const q = pickerSearch.toLowerCase();
    return raw.filter(item => item.name.toLowerCase().includes(q));
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={COLORS.primary} />
        <Text style={styles.loadingText}>Loading...</Text>
      </View>
    );
  }

  const currentModels = selectedBrand ? selectedBrand.models || [] : [];

  return (
    <>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled">

          {/* Supplier */}
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Supplier</Text>
            <TouchableOpacity
              style={styles.pickerBtn}
              onPress={() => { setPickerSearch(''); setPickerModal('supplier'); }}>
              <Text
                style={[
                  styles.pickerBtnText,
                  !selectedSupplier && styles.pickerBtnPlaceholder,
                ]}>
                {selectedSupplier ? selectedSupplier.name : 'Select Supplier...'}
              </Text>
              <Text style={styles.pickerArrow}>▼</Text>
            </TouchableOpacity>
          </View>

          {/* Brand + Model */}
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Phone Model</Text>
            <TouchableOpacity
              style={styles.pickerBtn}
              onPress={() => { setPickerSearch(''); setPickerModal('brand'); }}>
              <Text
                style={[
                  styles.pickerBtnText,
                  !selectedBrand && styles.pickerBtnPlaceholder,
                ]}>
                {selectedBrand ? selectedBrand.name : 'Select Brand...'}
              </Text>
              <Text style={styles.pickerArrow}>▼</Text>
            </TouchableOpacity>

            {selectedBrand && (
              <TouchableOpacity
                style={[styles.pickerBtn, {marginTop: 10}]}
                onPress={() => { setPickerSearch(''); setPickerModal('model'); }}>
                <Text
                  style={[
                    styles.pickerBtnText,
                    !selectedModel && styles.pickerBtnPlaceholder,
                  ]}>
                  {selectedModel ? selectedModel.name : 'Select Model...'}
                </Text>
                <Text style={styles.pickerArrow}>▼</Text>
              </TouchableOpacity>
            )}
          </View>

          {/* IMEI + Price entry */}
          {selectedModel && (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Add IMEI</Text>
              <TextInput
                style={styles.input}
                placeholder="IMEI (exactly 15 digits)"
                placeholderTextColor={COLORS.subtext}
                value={imeiInput}
                onChangeText={setImeiInput}
                keyboardType="number-pad"
                maxLength={15}
              />
              <View style={styles.priceRow}>
                <Text style={styles.priceLabel}>Purchase Price (PKR):</Text>
                <TextInput
                  style={styles.priceInput}
                  value={purchasePrice}
                  onChangeText={setPurchasePrice}
                  keyboardType="number-pad"
                />
              </View>
              <TouchableOpacity style={styles.addBtn} onPress={handleAddLine}>
                <Text style={styles.addBtnText}>+ Add to List</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Lines list */}
          {lines.length > 0 && (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Purchase Items ({lines.length})</Text>
              {lines.map((line, idx) => (
                <View key={line.imei} style={styles.lineItem}>
                  <View style={styles.lineHeader}>
                    <View style={styles.flex}>
                      <Text style={styles.lineModel}>{line.brand} {line.model}</Text>
                      <Text style={styles.lineImei}>{line.imei}</Text>
                    </View>
                    <View style={styles.lineRight}>
                      <Text style={styles.linePrice}>PKR {fmtPKR(line.purchase_price)}</Text>
                      <TouchableOpacity onPress={() => removeLine(line.imei)}>
                        <Text style={styles.lineRemove}>✕</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                </View>
              ))}

              <View style={styles.totalRow}>
                <Text style={styles.totalLabel}>TOTAL</Text>
                <Text style={styles.totalAmount}>PKR {fmtPKR(total)}</Text>
              </View>
            </View>
          )}

          <TouchableOpacity
            style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
            onPress={handleSave}
            disabled={saving}>
            {saving ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.saveBtnText}>Save Purchase</Text>
            )}
          </TouchableOpacity>

          <View style={styles.bottomPad} />
        </ScrollView>
      </KeyboardAvoidingView>

      {/* Picker Modal */}
      <Modal
        visible={pickerModal !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setPickerModal(null)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>
                {pickerModal === 'supplier'
                  ? 'Select Supplier'
                  : pickerModal === 'brand'
                  ? 'Select Brand'
                  : 'Select Model'}
              </Text>
              <TouchableOpacity onPress={() => setPickerModal(null)}>
                <Text style={styles.modalClose}>✕</Text>
              </TouchableOpacity>
            </View>
            {/* Search filter */}
            <View style={styles.modalSearch}>
              <TextInput
                style={styles.modalSearchInput}
                placeholder={
                  pickerModal === 'supplier'
                    ? 'Search supplier...'
                    : pickerModal === 'brand'
                    ? 'Search brand...'
                    : 'Search model...'
                }
                placeholderTextColor={COLORS.subtext}
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
                  style={styles.modalItem}
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
                  <Text style={styles.modalItemText}>{item.name}</Text>
                  {pickerModal === 'model' && (
                    <Text style={styles.modalItemSub}>
                      Ref: PKR {fmtPKR(item.reference_price)}
                    </Text>
                  )}
                </TouchableOpacity>
              )}
              ItemSeparatorComponent={() => <View style={styles.separator} />}
              keyboardShouldPersistTaps="handled"
            />
          </View>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  flex: {flex: 1},
  center: {flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.bg},
  loadingText: {marginTop: 12, color: COLORS.subtext},
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
  pickerBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 8,
    padding: 12,
  },
  pickerBtnText: {fontSize: 15, color: COLORS.text, flex: 1},
  pickerBtnPlaceholder: {color: COLORS.subtext},
  pickerArrow: {color: COLORS.subtext, fontSize: 12},
  input: {
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 8,
    padding: 11,
    fontSize: 15,
    color: COLORS.text,
    marginBottom: 10,
  },
  priceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
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
  addBtn: {
    backgroundColor: COLORS.primary,
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
  },
  addBtnText: {color: '#fff', fontWeight: 'bold', fontSize: 15},
  lineItem: {
    paddingBottom: 12,
    marginBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  lineHeader: {flexDirection: 'row', alignItems: 'flex-start'},
  lineModel: {fontSize: 14, fontWeight: '700', color: COLORS.text},
  lineImei: {fontSize: 12, color: COLORS.subtext, marginTop: 2},
  lineRight: {alignItems: 'flex-end', marginLeft: 8},
  linePrice: {fontSize: 14, fontWeight: '600', color: COLORS.primary},
  lineRemove: {fontSize: 18, color: COLORS.danger, marginTop: 4},
  totalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: '#E8F5E9',
    borderRadius: 8,
    padding: 12,
    marginTop: 4,
  },
  totalLabel: {fontSize: 16, fontWeight: 'bold', color: COLORS.primary},
  totalAmount: {fontSize: 18, fontWeight: 'bold', color: COLORS.primary},
  saveBtn: {
    backgroundColor: COLORS.primary,
    borderRadius: 10,
    padding: 16,
    alignItems: 'center',
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
    maxHeight: '70%',
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
});
