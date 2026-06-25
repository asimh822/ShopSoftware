/**
 * OwnerTodaySalesScreen — today's sold items grouped by brand then model.
 * Data fetched from Supabase: sale_vouchers → sale_lines → models → brands.
 * Pull to refresh.
 */

import React, {useState, useEffect, useCallback} from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
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
};

const SB_HEADERS = {
  apikey: SUPABASE_KEY,
  Authorization: `Bearer ${SUPABASE_KEY}`,
  'Content-Type': 'application/json',
};

function getTodayDDMMYYYY() {
  const d = new Date();
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return `${dd}/${mm}/${d.getFullYear()}`;
}

function arr(x) {
  return Array.isArray(x) ? x : [];
}

async function sbGet(path) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    headers: SB_HEADERS,
  });
  return res.json();
}

export default function OwnerTodaySalesScreen({navigation}) {
  const [brands, setBrands] = useState([]);
  const [grandQty, setGrandQty] = useState(0);
  const [grandRevenue, setGrandRevenue] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const loadData = useCallback(async () => {
    setError('');
    try {
      const today = getTodayDDMMYYYY();
      const todayEncoded = encodeURIComponent(today);

      // 1. Today's sale vouchers → sv_ids
      const svRows = await sbGet(
        `sale_vouchers?date=eq.${todayEncoded}&select=id`,
      );
      const svIds = arr(svRows)
        .map(r => r.id)
        .filter(Boolean);

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
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const onRefresh = () => {
    setRefreshing(true);
    loadData();
  };

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
            <Text style={styles.emptyText}>No sales recorded today</Text>
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
