/**
 * Owner PIN session — module-level variable, lives for the app process lifetime.
 * Cleared on app restart (not persisted to AsyncStorage by design).
 */

let _ownerPin = null;

export const setOwnerPin = pin => {
  _ownerPin = pin;
};

export const getOwnerPin = () => _ownerPin;

export const clearOwnerPin = () => {
  _ownerPin = null;
};
