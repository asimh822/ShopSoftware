/**
 * United Mobile EPOS — React Native App
 * Root navigation + auth check
 */

import React, {useEffect, useState} from 'react';
import {View, ActivityIndicator, StyleSheet} from 'react-native';
import {NavigationContainer} from '@react-navigation/native';
import {createStackNavigator} from '@react-navigation/stack';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {GestureHandlerRootView} from 'react-native-gesture-handler';

import SetupScreen from './src/screens/SetupScreen';
import LoginScreen from './src/screens/LoginScreen';
import HomeScreen from './src/screens/HomeScreen';
import NewSaleScreen from './src/screens/NewSaleScreen';
import NewPurchaseScreen from './src/screens/NewPurchaseScreen';
import StockCheckScreen from './src/screens/StockCheckScreen';
import MyTodayScreen from './src/screens/MyTodayScreen';

const Stack = createStackNavigator();

const COLORS = {
  primary: '#1565C0',
  background: '#F5F5F5',
};

export default function App() {
  const [initialRoute, setInitialRoute] = useState(null); // null = loading

  useEffect(() => {
    checkStartup();
  }, []);

  const checkStartup = async () => {
    try {
      const serverUrl = await AsyncStorage.getItem('server_url');
      const token = await AsyncStorage.getItem('auth_token');

      if (!serverUrl) {
        setInitialRoute('Setup');
      } else if (!token) {
        setInitialRoute('Login');
      } else {
        setInitialRoute('Home');
      }
    } catch {
      setInitialRoute('Setup');
    }
  };

  if (initialRoute === null) {
    return (
      <GestureHandlerRootView style={styles.flex}>
        <View style={styles.loader}>
          <ActivityIndicator size="large" color={COLORS.primary} />
        </View>
      </GestureHandlerRootView>
    );
  }

  return (
    <GestureHandlerRootView style={styles.flex}>
      <NavigationContainer>
        <Stack.Navigator
          initialRouteName={initialRoute}
          screenOptions={{
            headerStyle: {backgroundColor: COLORS.primary},
            headerTintColor: '#fff',
            headerTitleStyle: {fontWeight: 'bold'},
            headerBackTitleVisible: false,
          }}>
          <Stack.Screen
            name="Setup"
            component={SetupScreen}
            options={{title: 'Server Setup', headerLeft: null}}
          />
          <Stack.Screen
            name="Login"
            component={LoginScreen}
            options={{title: 'United Mobile', headerLeft: null}}
          />
          <Stack.Screen
            name="Home"
            component={HomeScreen}
            options={{title: 'United Mobile EPOS', headerLeft: null}}
          />
          <Stack.Screen
            name="NewSale"
            component={NewSaleScreen}
            options={{title: 'New Sale'}}
          />
          <Stack.Screen
            name="NewPurchase"
            component={NewPurchaseScreen}
            options={{title: 'New Purchase'}}
          />
          <Stack.Screen
            name="StockCheck"
            component={StockCheckScreen}
            options={{title: 'Stock Check'}}
          />
          <Stack.Screen
            name="MyToday"
            component={MyTodayScreen}
            options={{title: "Today's Summary"}}
          />
        </Stack.Navigator>
      </NavigationContainer>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  flex: {flex: 1},
  loader: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: COLORS.background,
  },
});
