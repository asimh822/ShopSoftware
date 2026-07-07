/**
 * OwnerTodaySalesScreen — sold items grouped by brand then model, for a
 * date range and sale-type filter (defaults to today, all types).
 * Data fetched from Supabase: sale_vouchers → sale_lines → models → brands.
 * Pull to refresh.
 */

import React, {useState, useEffect, useCallback} from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TextInput,
  Pressable,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import {fmtPKR} from '../utils/formatting';
import {SUPABASE_URL, SUPABASE_KEY} from '../supabaseConfig';

const COLORS = {
  bg: '#F5F5F5',
  card: '#FFFFFF',
  primary: '#37474F',
  brandBg: '#ECEFF1',
  brandText: '#263238',
  modelText: '#424242',
  subtext: '#757575',
  border: '#E0E0E0',
  footerBg: '#263238',
  chipBg: '#ECEFF1',
  chipText: '#455A64',
  chipActiveBg: '#37474F',
  chipActiveText: '#FFFFFF',
  inputBg: '#FFFFFF',
  inputBorder: '#CFD8DC',
  errorText: '#B71C1C',
};

const SB_HEADERS = {
  apikey: SUPABASE_KEY,
  Authorization: `Bearer ${SUPABASE_KEY}`,
  'Content-Type': 'application/json',
};

function arr(x) {
  return Array.isArray(x) ? x : [];
}

async function sbGet(path) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    headers: SB_HEADERS,
  });
  return res.json();
}

function pad2(n) {
  return String(n).padStart(2, '0');
}

function formatDMY(d) {
  return `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()}`;
}

function formatDM(d) {
  return `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}`;
}

// sale_vouchers.date is stored/mirrored as DD/MM/YYYY text — parse to a
// comparable Date rather than doing a raw string gte/lte (which sorts wrong
// across month boundaries, e.g. "05/07/2026" vs "28/06/2026").
function parseDDMMYYYY(s) {
  const [dd, mm, yyyy] = s.split('/').map(Number);
  return new Date(yyyy, mm - 1, dd);
}

function startOfDay(d) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0);
}

function endOfDay(d) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);
}

function isSameYMD(a, b) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function computeRangeLabel(fromDate, toDate) {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);

  if (isSameYMD(fromDate, today) && isSameYMD(toDate, today)) {
    return 'Today';
  }
  if (isSameYMD(fromDate, yesterday) && isSameYMD(toDate, yesterday)) {
    return 'Yesterday';
  }
  if (isSameYMD(fromDate, monthStart) && isSameYMD(toDate, today)) {
    return 'This Month';
  }
  return `${formatDM(fromDate)} – ${formatDM(toDate)}`;
}

export default function OwnerTodaySalesScreen({navigation}) {
  const [brands, setBrands] = useState([]);
  const [grandQty, setGrandQty] = useState(0);
  const [grandRevenue, setGrandRevenue] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const [fromDate, setFromDate] = useState(new Date());
  const [toDate, setToDate] = useState(new Date());
  const [saleType, setSaleType] = useState('all'); // 'all' | 'cash' | 'credit'

  const [fromText, setFromText] = useState(formatDMY(new Date()));
  const [toText, setToText] = useState(formatDMY(new Date()));
  const [dateError, setDateError] = useState('');

  const loadData = useCallback(async () => {
    setError('');
    try {
      // 1. All sale vouchers, filtered client-side by date range + type
      const allSvRows = await sbGet('sale_vouchers?select=id,date,type&limit=20000');
      const fromStart = startOfDay(fromDate);
      const toEnd = endOfDay(toDate);
      const svRows = arr(allSvRows).filter(r => {
        if (!r.date) return false;
        const d = parseDDMMYYYY(r.date);
        if (isNaN(d.getTime())) return false;
        const inRange = d >= fromStart && d <= toEnd;
        const typeOk = saleType === 'all' || r.type === saleType;
        return inRange && typeOk;
      });
      const svIds = svRows.map(r => r.id).filter(Boolean);

      if (svIds.length === 0) {
        setBrands([]);
        setGrandQty(0);
        setGrandRevenue(0);
        return;
      }

      // 2. Sale lines for those vouchers
      const slRows = await sbGet(
        `sale_lines?sv_id=in.(${svIds.join(',')})&select=model_id,final_price`,
      );

      const modelIds = [
        ...new Set(arr(slRows).map(r => r.model_id).filter(Boolean)),
      ];
      if (modelIds.length === 0) {
        setBrands([]);
        setGrandQty(0);
        setGrandRevenue(0);
        return;
      }

      // 3. Models (name + brand_id)
      const modRows = await sbGet(
        `models?id=in.(${modelIds.join(',')})&select=id,name,brand_id`,
      );
      const modMap = {};
      arr(modRows).forEach(m => {
        modMap[m.id] = m;
      });

      // 4. Brands (name)
      const brandIds = [
        ...new Set(arr(modRows).map(r => r.brand_id).filter(Boolean)),
      ];
      const brandRows = await sbGet(
        `brands?id=in.(${brandIds.join(',')})&select=id,name`,
      );
      const brandMap = {};
      arr(brandRows).forEach(b => {
        brandMap[b.id] = b.name;
      });

      // 5. Group sale lines by brand → model
      const brandsMap = {};
      arr(slRows).forEach(sl => {
        const mod = modMap[sl.model_id];
        if (!mod) {
          return;
        }
        const brandName = brandMap[mod.brand_id] || 'Unknown';
        const modelName = mod.name;

        if (!brandsMap[brandName]) {
          brandsMap[brandName] = {
            brand: brandName,
            models: {},
            brand_total_qty: 0,
            brand_total_revenue: 0,
          };
        }
        if (!brandsMap[brandName].models[modelName]) {
          brandsMap[brandName].models[modelName] = {
            model: modelName,
            quantity: 0,
            revenue: 0,
          };
        }
        brandsMap[brandName].models[modelName].quantity += 1;
        brandsMap[brandName].models[modelName].revenue += sl.final_price || 0;
        brandsMap[brandName].brand_total_qty += 1;
        brandsMap[brandName].brand_total_revenue += sl.final_price || 0;
      });

      const brandsList = Object.values(brandsMap)
        .map(b => ({
          ...b,
          models: Object.values(b.models),
          brand_total_revenue: Math.round(b.brand_total_revenue * 100) / 100,
        }))
        .sort((a, b) => a.brand.localeCompare(b.brand));

      const gQty = brandsList.reduce((s, b) => s + b.brand_total_qty, 0);
      const gRev = Math.round(
        brandsList.reduce((s, b) => s + b.brand_total_revenue, 0) * 100,
      ) / 100;

      setBrands(brandsList);
      setGrandQty(gQty);
      setGrandRevenue(gRev);
    } catch (err) {
      setError('Failed to load');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [fromDate, toDate, saleType]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (navigation && navigation.setOptions) {
      navigation.setOptions({title: computeRangeLabel(fromDate, toDate)});
    }
  }, [navigation, fromDate, toDate]);

  const onRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const applyRange = (from, to) => {
    setDateError('');
    setFromDate(from);
    setToDate(to);
    setFromText(formatDMY(from));
    setToText(formatDMY(to));
  };

  const setQuickToday = () => {
    const t = new Date();
    applyRange(t, t);
  };

  const setQuickYesterday = () => {
    const y = new Date();
    y.setDate(y.getDate() - 1);
    applyRange(y, y);
  };

  const setQuickThisMonth = () => {
    const now = new Date();
    const first = new Date(now.getFullYear(), now.getMonth(), 1);
    applyRange(first, now);
  };

  const applyManualDates = () => {
    const from = parseDDMMYYYY(fromText.trim());
    const to = parseDDMMYYYY(toText.trim());
    if (isNaN(from.getTime()) || isNaN(to.getTime())) {
      setDateError('Enter valid dates as DD/MM/YYYY');
      return;
    }
    if (from > to) {
      setDateError('"From" date must not be after "To" date');
      return;
    }
    setDateError('');
    setFromDate(from);
    setToDate(to);
  };

  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
  const isToday = isSameYMD(fromDate, today) && isSameYMD(toDate, today);
  const isYesterday =
    isSameYMD(fromDate, yesterday) && isSameYMD(toDate, yesterday);
  const isThisMonth =
    isSameYMD(fromDate, monthStart) && isSameYMD(toDate, today);

  // Flatten brands → [brand_header, model_row, model_row, ...]
  const listData = [];
  brands.forEach(b => {
    listData.push({type: 'brand', ...b});
    b.models.forEach(m => listData.push({type: 'model', brand: b.brand, ...m}));
  });

  const renderItem = ({item}) => {
    if (item.type === 'brand') {
      return (
        <View style={styles.brandRow}>
          <Text style={styles.brandName}>{item.brand}</Text>
          <View style={styles.brandRight}>
            <Text style={styles.brandQty}>{item.brand_total_qty} units</Text>
            <Text style={styles.brandRevenue}>
              Rs. {fmtPKR(item.brand_total_revenue)}
            </Text>
          </View>
        </View>
      );
    }
    return (
      <View style={styles.modelRow}>
        <Text style={styles.modelName}>{item.model}</Text>
        <Text style={styles.modelQty}>{item.quantity}</Text>
        <Text style={styles.modelRevenue}>Rs. {fmtPKR(item.revenue)}</Text>
      </View>
    );
  };

  const filterHeader = (
    <View style={styles.filterCard}>
      <View style={styles.chipRow}>
        <Pressable
          style={[styles.chip, isToday && styles.chipActive]}
          onPress={setQuickToday}>
          <Text style={[styles.chipText, isToday && styles.chipTextActive]}>
            Today
          </Text>
        </Pressable>
        <Pressable
          style={[styles.chip, isYesterday && styles.chipActive]}
          onPress={setQuickYesterday}>
          <Text style={[styles.chipText, isYesterday && styles.chipTextActive]}>
            Yesterday
          </Text>
        </Pressable>
        <Pressable
          style={[styles.chip, isThisMonth && styles.chipActive]}
          onPress={setQuickThisMonth}>
          <Text
            style={[styles.chipText, isThisMonth && styles.chipTextActive]}>
            This Month
          </Text>
        </Pressable>
      </View>

      <View style={styles.dateRow}>
        <View style={styles.dateField}>
          <Text style={styles.dateLabel}>From</Text>
          <TextInput
            style={styles.dateInput}
            value={fromText}
            onChangeText={setFromText}
            placeholder="DD/MM/YYYY"
            placeholderTextColor={COLORS.subtext}
          />
        </View>
        <View style={styles.dateField}>
          <Text style={styles.dateLabel}>To</Text>
          <TextInput
            style={styles.dateInput}
            value={toText}
            onChangeText={setToText}
            placeholder="DD/MM/YYYY"
            placeholderTextColor={COLORS.subtext}
          />
        </View>
        <Pressable style={styles.searchBtn} onPress={applyManualDates}>
          <Text style={styles.searchBtnText}>Search</Text>
        </Pressable>
      </View>
      {dateError ? <Text style={styles.dateError}>{dateError}</Text> : null}

      <View style={styles.typeRow}>
        {[
          {key: 'all', label: 'All'},
          {key: 'cash', label: 'Cash'},
          {key: 'credit', label: 'Credit'},
        ].map(t => (
          <Pressable
            key={t.key}
            style={[styles.typeChip, saleType === t.key && styles.chipActive]}
            onPress={() => setSaleType(t.key)}>
            <Text
              style={[
                styles.chipText,
                saleType === t.key && styles.chipTextActive,
              ]}>
              {t.label}
            </Text>
          </Pressable>
        ))}
      </View>
    </View>
  );

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>{error}</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={listData}
        keyExtractor={(item, idx) =>
          item.type === 'brand'
            ? `brand-${item.brand}`
            : `model-${item.brand}-${item.model}-${idx}`
        }
        renderItem={renderItem}
        ListHeaderComponent={filterHeader}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            colors={[COLORS.primary]}
          />
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyIcon}>📋</Text>
            <Text style={styles.emptyText}>No sales recorded for this period</Text>
          </View>
        }
      />

      {listData.length > 0 && (
        <View style={styles.footer}>
          <Text style={styles.footerLabel}>Grand Total</Text>
          <Text style={styles.footerQty}>{grandQty} units</Text>
          <Text style={styles.footerRevenue}>Rs. {fmtPKR(grandRevenue)}</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: COLORS.bg},
  center: {flex: 1, justifyContent: 'center', alignItems: 'center'},
  errorText: {fontSize: 15, color: '#B71C1C'},
  content: {padding: 12, paddingBottom: 80},
  filterCard: {
    backgroundColor: COLORS.card,
    borderRadius: 10,
    padding: 12,
    marginBottom: 4,
    elevation: 1,
    shadowColor: '#000',
    shadowOpacity: 0.06,
    shadowRadius: 3,
    shadowOffset: {width: 0, height: 1},
  },
  chipRow: {
    flexDirection: 'row',
    marginBottom: 10,
  },
  chip: {
    backgroundColor: COLORS.chipBg,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    marginRight: 8,
  },
  chipActive: {
    backgroundColor: COLORS.chipActiveBg,
  },
  chipText: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.chipText,
  },
  chipTextActive: {
    color: COLORS.chipActiveText,
  },
  dateRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
  },
  dateField: {
    flex: 1,
    marginRight: 8,
  },
  dateLabel: {
    fontSize: 11,
    color: COLORS.subtext,
    marginBottom: 4,
  },
  dateInput: {
    borderWidth: 1,
    borderColor: COLORS.inputBorder,
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
    fontSize: 13,
    color: COLORS.brandText,
    backgroundColor: COLORS.inputBg,
  },
  searchBtn: {
    backgroundColor: COLORS.primary,
    borderRadius: 6,
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  searchBtnText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 12,
  },
  dateError: {
    color: COLORS.errorText,
    fontSize: 11,
    marginTop: 6,
  },
  typeRow: {
    flexDirection: 'row',
    marginTop: 10,
  },
  typeChip: {
    backgroundColor: COLORS.chipBg,
    paddingHorizontal: 16,
    paddingVertical: 6,
    borderRadius: 16,
    marginRight: 8,
  },
  brandRow: {
    backgroundColor: COLORS.brandBg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginTop: 10,
    borderRadius: 8,
    borderLeftWidth: 4,
    borderLeftColor: COLORS.primary,
  },
  brandName: {
    fontSize: 14,
    fontWeight: 'bold',
    color: COLORS.brandText,
    flex: 1,
  },
  brandRight: {
    alignItems: 'flex-end',
  },
  brandQty: {
    fontSize: 12,
    color: COLORS.subtext,
  },
  brandRevenue: {
    fontSize: 14,
    fontWeight: 'bold',
    color: COLORS.brandText,
    marginTop: 2,
  },
  modelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
    backgroundColor: COLORS.card,
  },
  modelName: {
    flex: 1,
    fontSize: 13,
    color: COLORS.modelText,
  },
  modelQty: {
    fontSize: 13,
    color: COLORS.subtext,
    width: 36,
    textAlign: 'center',
  },
  modelRevenue: {
    fontSize: 13,
    fontWeight: '600',
    color: COLORS.modelText,
    textAlign: 'right',
    minWidth: 100,
  },
  empty: {
    alignItems: 'center',
    paddingTop: 60,
  },
  emptyIcon: {fontSize: 48, marginBottom: 12},
  emptyText: {fontSize: 16, color: COLORS.subtext},
  footer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: COLORS.footerBg,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  footerLabel: {
    flex: 1,
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 14,
  },
  footerQty: {
    color: 'rgba(255,255,255,0.75)',
    fontSize: 13,
    marginRight: 16,
  },
  footerRevenue: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 15,
  },
});
