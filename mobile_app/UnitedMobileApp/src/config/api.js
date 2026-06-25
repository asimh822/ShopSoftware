/**
 * API helper — wraps axios with auth token management.
 * All screens import { apiGet, apiPost, clearSession } from here.
 *
 * Server URL: use the DDNS address (e.g. http://unitedmobile.ddns.net:5000)
 * so the app works both on local Wi-Fi and remotely over the internet.
 * On local Wi-Fi only, the LAN IP (http://192.168.x.x:5000) also works.
 */

import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

// ---------- internal helpers ----------

async function getBaseUrl() {
  const url = await AsyncStorage.getItem('server_url');
  if (!url) throw new Error('Server URL not configured. Go to Setup.');
  return url.replace(/\/$/, ''); // strip trailing slash
}

async function getToken() {
  return await AsyncStorage.getItem('auth_token');
}

function buildHeaders(token) {
  const h = {'Content-Type': 'application/json'};
  if (token) h['Authorization'] = `Bearer ${token}`;
  return h;
}

// ---------- session ----------

export async function clearSession() {
  await AsyncStorage.multiRemove(['auth_token', 'salesman_id', 'salesman_name']);
}

export async function saveSession(token, salesman_id, salesman_name) {
  await AsyncStorage.multiSet([
    ['auth_token', String(token)],
    ['salesman_id', String(salesman_id)],
    ['salesman_name', salesman_name],
  ]);
}

export async function getSalesmanId() {
  return await AsyncStorage.getItem('salesman_id');
}

export async function getSalesmanName() {
  return await AsyncStorage.getItem('salesman_name');
}

// ---------- public: no auth ----------

export async function apiPing() {
  const base = await getBaseUrl();
  const resp = await axios.get(`${base}/api/ping`, {timeout: 5000});
  return resp.data;
}

export async function apiHealth(baseUrl) {
  // Uses the URL passed directly (before it's saved) so setup screen can test it.
  // validateStatus: () => true  — axios never throws for any HTTP status code;
  // only a real network error / timeout will throw here.
  const base = (baseUrl || (await getBaseUrl())).replace(/\/$/, '');
  const resp = await axios.get(`${base}/api/health`, {
    timeout: 8000,
    validateStatus: () => true, // treat every HTTP response as "server reachable"
  });
  return resp.data;
}

export async function apiLogin(pin) {
  const base = await getBaseUrl();
  const resp = await axios.post(
    `${base}/api/login`,
    {pin},
    {headers: {'Content-Type': 'application/json'}, timeout: 8000},
  );
  return resp.data;
}

// ---------- authenticated ----------

export async function apiGet(path, params = {}) {
  const base = await getBaseUrl();
  const token = await getToken();
  try {
    const resp = await axios.get(`${base}${path}`, {
      headers: buildHeaders(token),
      params,
      timeout: 10000,
    });
    return resp.data;
  } catch (err) {
    if (err.response?.status === 401) {
      await clearSession();
      throw new Error('SESSION_EXPIRED');
    }
    throw err;
  }
}

// ---------- owner (X-Owner-Pin header, no salesman token required) ----------

export async function apiOwnerGet(path, ownerPin, params = {}) {
  const base = await getBaseUrl();
  const token = await getToken();
  try {
    const resp = await axios.get(`${base}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(token ? {Authorization: `Bearer ${token}`} : {}),
        'X-Owner-Pin': ownerPin,
      },
      params,
      timeout: 10000,
    });
    return resp.data;
  } catch (err) {
    if (err.response?.status === 401) {
      throw new Error('OWNER_AUTH_FAILED');
    }
    throw err;
  }
}

export async function apiPost(path, body = {}) {
  const base = await getBaseUrl();
  const token = await getToken();
  try {
    const resp = await axios.post(`${base}${path}`, body, {
      headers: buildHeaders(token),
      timeout: 15000,
    });
    return resp.data;
  } catch (err) {
    if (err.response?.status === 401) {
      await clearSession();
      throw new Error('SESSION_EXPIRED');
    }
    // Return the server error body if available so screens can show it
    if (err.response?.data) {
      const e = new Error(err.response.data.error || 'Server error');
      e.serverData = err.response.data;
      throw e;
    }
    throw err;
  }
}
