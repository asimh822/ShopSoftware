/**
 * United Mobile EPOS — React Native App
 * Entry point
 *
 * IMPORTANT: gesture-handler import MUST be first line before any other imports.
 */
import 'react-native-gesture-handler';

import {AppRegistry} from 'react-native';
import App from './App';
import {name as appName} from './app.json';

AppRegistry.registerComponent(appName, () => App);
