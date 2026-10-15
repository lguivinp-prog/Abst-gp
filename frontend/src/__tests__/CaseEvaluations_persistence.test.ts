import { test } from 'node:test';
import assert from 'node:assert/strict';

/**
 * Pure state reducer simulating the exact view persistence logic in CaseEvaluations.tsx
 */
interface ViewState {
  caseId: string;
  activeView: 'matrix' | 'cards';
  userManuallyToggled: boolean;
}

function initCase(caseId: string): ViewState {
  return {
    caseId,
    activeView: 'cards',
    userManuallyToggled: false
  };
}

function handleSelectView(state: ViewState, view: 'matrix' | 'cards'): ViewState {
  return {
    ...state,
    activeView: view,
    userManuallyToggled: true
  };
}

function handleLoadData(state: ViewState, offerCount: number): ViewState {
  if (!state.userManuallyToggled) {
    return {
      ...state,
      activeView: offerCount >= 2 ? 'matrix' : 'cards'
    };
  }
  // User manually chose view: preserve preference
  return { ...state };
}

function handleCaseChange(state: ViewState, newCaseId: string, newOfferCount: number): ViewState {
  const resetState = initCase(newCaseId);
  return handleLoadData(resetState, newOfferCount);
}

test('Una oferta inicializa vista en Detalle por Oferta (cards)', () => {
  let state = initCase('case-1');
  state = handleLoadData(state, 1);
  assert.equal(state.activeView, 'cards');
  assert.equal(state.userManuallyToggled, false);
});

test('Dos o más ofertas inicializan vista en Matriz Multiproveedor (matrix)', () => {
  let state = initCase('case-2');
  state = handleLoadData(state, 3);
  assert.equal(state.activeView, 'matrix');
  assert.equal(state.userManuallyToggled, false);
});

test('Operador cambia manualmente a cards y loadData/reevaluación conserva la preferencia', () => {
  let state = initCase('case-3');
  state = handleLoadData(state, 2);
  assert.equal(state.activeView, 'matrix');

  // Operador cambia manualmente
  state = handleSelectView(state, 'cards');
  assert.equal(state.activeView, 'cards');
  assert.equal(state.userManuallyToggled, true);

  // Actualización de datos / reevaluación (loadData) no restablece la preferencia manual
  state = handleLoadData(state, 2);
  assert.equal(state.activeView, 'cards');

  // Incluso si el número de ofertas cambia a 3
  state = handleLoadData(state, 3);
  assert.equal(state.activeView, 'cards');
});

test('Operador cambia manualmente a matrix en caso de 1 oferta y loadData la conserva', () => {
  let state = initCase('case-4');
  state = handleLoadData(state, 1);
  assert.equal(state.activeView, 'cards');

  state = handleSelectView(state, 'matrix');
  assert.equal(state.activeView, 'matrix');

  state = handleLoadData(state, 1);
  assert.equal(state.activeView, 'matrix');
});

test('Cambio de expediente restablece la preferencia manual e inicializa según sus propias ofertas', () => {
  let state = initCase('case-5');
  state = handleLoadData(state, 2); // default matrix
  state = handleSelectView(state, 'cards'); // manual override to cards
  assert.equal(state.activeView, 'cards');

  // Cambio a un nuevo expediente con 2 ofertas
  state = handleCaseChange(state, 'case-6', 2);
  assert.equal(state.caseId, 'case-6');
  assert.equal(state.userManuallyToggled, false);
  assert.equal(state.activeView, 'matrix'); // inicializa correctamente su propia vista

  // Cambio a un expediente con 1 oferta
  state = handleCaseChange(state, 'case-7', 1);
  assert.equal(state.caseId, 'case-7');
  assert.equal(state.userManuallyToggled, false);
  assert.equal(state.activeView, 'cards'); // inicializa correctamente su propia vista
});
