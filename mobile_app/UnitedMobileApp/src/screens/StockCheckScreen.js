/**
 * StockCheckScreen — search stock by IMEI digits or model name.
 * Shows brand → model → IMEI list (expandable).
 * Pull-to-refresh.
 */

import React, {useState, useEffect, useCallback, useRef} from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  FlatList,
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  Platform,
} from 'react-native';
import {apiGet} from '../config/api';
import {fmtPKR} from '../utils/formatting';

const COLORS = {
  primary: '#E65100',
  bg: '#F5F5F5',
  card: '#FFFFFF',
  border: '#E0E0E0',
  text: '#212121',
  subtext: '#757575',
  success: '#2E7D32',
};

export default function StockCheckScreen({navigation}) {
  const [query, setQuery] = useState('');
  const [groups, setGroups] = useState([]); // [{brand, models:[{model, qty, imeis:[]}]}]
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [expanded, setExpanded] = useState({}); // key = "brand|model"
  const [totalUnits, setTotalUnits] = useState(0);
  const [error, setError] = useState(null);

  const debounceRef = useRef(null);

  useEffect(() => {
    loadStock('');
  }, []);

  const loadStock = useCallback(async (searchQuery) => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (searchQuery && searchQuery.trim()) {
        params.search = searchQuery.trim();
      }
      const data = await apiGet('/api/stock', params);

      if (!data || !data.success) {
        setError('Server returned an unexpected response.');
        setGroups([]);
        setTotalUnits(0);
        return;
      }

      const raw = data.stock || [];

      // Group by brand → model
      const brandMap = {};
      let total = 0;
      raw.forEach(item => {
        const brand = item.brand || 'Unknown';
        const model = item.model || 'Unknown';
        if (!brandMap[brand]) brandMap[brand] = {};
        if (!brandMap[brand][model]) {
          brandMap[brand][model] = {
            model_id: item.model_id,
            qty: 0,
            imeis: [],
          };
        }
        brandMap[brand][model].qty++;
        brandMap[brand][model].imeis.push(item.imei);
        total++;
      });

      const grouped = Object.keys(brandMap)
        .sort()
        .map(brand => ({
          brand,
          models: Object.keys(brandMap[brand])
            .sort()
            .map(model => ({
              model,
              qty: brandMap[brand][model].qty,
              imeis: brandMap[brand][model].imeis,
            })),
          totalQty: Object.values(brandMap[brand]).reduce((s, m) => s + m.qty, 0),
        }));

      setGroups(grouped);
      setTotalUnits(total);
    } catch (err) {
      if (err.message === 'SESSION_EXPIRED') {
        navigation.replace('Login');
      } else {
        const msg = err?.response?.data?.error || err?.message || 'Failed to load stock.';
        setError(msg);
        setGroups([]);
        setTotalUnits(0);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const handleQueryChange = (text) => {
    setQuery(text);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      loadStock(text);
    }, 400);
  };

  const onRefresh = () => {
    setRefreshing(true);
    loadStock(query);
  };

  const toggleModel = (key) => {
    setExpanded(prev => ({...prev, [key]: !prev[key]}));
  };

  const renderGroup = ({item: group}) => (
    <View style={styles.brandCard}>
      <View style={styles.brandHeader}>
        <Text style={styles.brandName}>{group.brand}</Text>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>{group.totalQty}</Text>
        </View>
      </View>
      {group.models.map(m => {
        const key = `${group.brand}|${m.model}`;
        const open = expanded[key];
        return (
          <View key={key}>
            <TouchableOpacity
              style={styles.modelRow}
              onPress={() => toggleModel(key)}
              activeOpacity={0.7}>
              <Text style={styles.modelName}>{m.model}</Text>
              <View style={styles.modelRight}>
                <View style={styles.qtyBadge}>
                  <Text style={styles.qtyText}>{m.qty}</Text>
                </View>
                <Text style={styles.expandIcon}>{open ? '▲' : '▼'}</Text>
              </View>
            </TouchableOpacity>
            {open && (
              <View style={styles.imeiList}>
                {m.imeis.map(imei => (
                  <Text key={imei} style={styles.imeiRow}>
                    • {imei}
                  </Text>
                ))}
              </View>
            )}
          </View>
        );
      })}
    </View>
  );

  return (
    <View style={styles.container}>
      {/* Search bar */}
      <View style={styles.searchBar}>
        <Text style={styles.searchIcon}>🔍</Text>
        <TextInput
          style={styles.searchInput}
          placeholder="Search by model or last 5 IMEI digits..."
          placeholderTextColor={COLORS.subtext}
          value={query}
          onChangeText={handleQueryChange}
          autoCapitalize="none"
        />
        {query.length > 0 && (
          <TouchableOpacity onPress={() => handleQueryChange('')}>
            <Text style={styles.clearBtn}>✕</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Summary bar */}
      <View style={styles.summaryBar}>
        <Text style={styles.summaryText}>
          {loading ? 'Loading...' : `${totalUnits} phone${totalUnits !== 1 ? 's' : ''} in stock`}
        </Text>
      </View>

      {loading && !refreshing ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={COLORS.primary} />
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Text style={styles.errorText}>⚠️ {error}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={() => loadStock(query)}>
            <Text style={styles.retryBtnText}>Retry</Text>
          </TouchableOpacity>
        </View>
      ) : groups.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.emptyText}>
            {query ? 'No stock found matching your search.' : 'No stock available.'}
          </Text>
        </View>
      ) : (
        <FlatList
          data={groups}
          keyExtractor={item => item.brand}
          renderItem={renderGroup}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              colors={[COLORS.primary]}
            />
          }
          keyboardShouldPersistTaps="handled"
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: COLORS.bg},
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    margin: 12,
    borderRadius: 10,
    paddingHorizontal: 12,
    elevation: 2,
    shadowColor: '#000',
    shadowOpacity: 0.08,
    shadowRadius: 4,
    shadowOffset: {width: 0, height: 2},
  },
  searchIcon: {fontSize: 16, marginRight: 8},
  searchInput: {
    flex: 1,
    fontSize: 15,
    color: COLORS.text,
    paddingVertical: 12,
  },
  clearBtn: {fontSize: 16, color: COLORS.subtext, padding: 4},
  summaryBar: {
    paddingHorizontal: 16,
    paddingBottom: 8,
  },
  summaryText: {fontSize: 13, color: COLORS.subtext},
  center: {flex: 1, justifyContent: 'center', alignItems: 'center', padding: 20},
  emptyText: {fontSize: 15, color: COLORS.subtext, textAlign: 'center', padding: 30},
  errorText: {
    fontSize: 14,
    color: '#C62828',
    textAlign: 'center',
    marginBottom: 16,
    lineHeight: 22,
  },
  retryBtn: {
    backgroundColor: COLORS.primary,
    borderRadius: 8,
    paddingHorizontal: 24,
    paddingVertical: 10,
  },
  retryBtnText: {color: '#fff', fontWeight: 'bold', fontSize: 14},
  listContent: {padding: 12, paddingTop: 0},
  brandCard: {
    backgroundColor: COLORS.card,
    borderRadius: 10,
    marginBottom: 12,
    overflow: 'hidden',
    elevation: 2,
    shadowColor: '#000',
    shadowOpacity: 0.06,
    shadowRadius: 3,
    shadowOffset: {width: 0, height: 1},
  },
  brandHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: COLORS.primary,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  brandName: {fontSize: 16, fontWeight: 'bold', color: '#fff'},
  badge: {
    backgroundColor: 'rgba(255,255,255,0.25)',
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 2,
  },
  badgeText: {color: '#fff', fontWeight: 'bold', fontSize: 13},
  modelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  modelName: {fontSize: 15, color: COLORS.text, flex: 1},
  modelRight: {flexDirection: 'row', alignItems: 'center'},
  qtyBadge: {
    backgroundColor: '#FFF3E0',
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 2,
    marginRight: 10,
  },
  qtyText: {color: COLORS.primary, fontWeight: 'bold', fontSize: 13},
  expandIcon: {color: COLORS.subtext, fontSize: 11},
  imeiList: {
    paddingHorizontal: 24,
    paddingBottom: 12,
    paddingTop: 6,
    backgroundColor: '#FAFAFA',
  },
  imeiRow: {
    fontSize: 13,
    color: COLORS.subtext,
    paddingVertical: 3,
    fontFamily: Platform ? 'monospace' : undefined,
  },
});
