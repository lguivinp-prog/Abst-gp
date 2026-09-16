import { test } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { CaseSummary } from '../features/cases/components/CaseSummary';

test('CaseSummary renders "Cargar requerimiento" when no document exists', () => {
  // We mock useRequirementDocument via a very simple hook override, but since it's hard to mock in node test,
  // maybe it's better to just write a simple test for CaseSummary.
  // Wait, CaseSummary uses useRequirementDocument which calls useState/useEffect.
  // renderToStaticMarkup handles useState but ignores useEffect.
  // Since initial state of useRequirementDocument has isNotAvailable=false, blobUrl=null, isLoading=false,
  // it should render "Cargar requerimiento".

  const mockCaseData: any = {
    id: 1,
    title: 'Test Case',
    status: 'CREATED',
    created_at: '2023-01-01',
    contract_type: 'goods',
  };

  const html = renderToStaticMarkup(React.createElement(CaseSummary, { caseData: mockCaseData }));
  
  assert.ok(html.includes('Cargar requerimiento'), 'HTML must contain Cargar requerimiento');
});
