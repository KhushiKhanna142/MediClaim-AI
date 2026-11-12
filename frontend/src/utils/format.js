export function formatINR(val) {
  if (val === null || val === undefined || Number.isNaN(Number(val))) {
    return '₹ 0';
  }
  const num = Number(val);
  const neg = num < 0;
  const abs = Math.abs(num);
  const hasCents = abs % 1 >= 0.01;
  const intPart = Math.floor(abs).toString();
  const cents = hasCents ? (abs % 1).toFixed(2).substring(1) : '';

  let formatted = intPart;
  if (intPart.length > 3) {
    const last3 = intPart.slice(-3);
    let rem = intPart.slice(0, -3);
    const parts = [];
    while (rem.length > 2) {
      parts.unshift(rem.slice(-2));
      rem = rem.slice(0, -2);
    }
    if (rem) parts.unshift(rem);
    formatted = parts.join(',') + ',' + last3;
  }

  return `${neg ? '-' : ''}₹ ${formatted}${cents}`;
}

export function formatDate(dateStr) {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

export const POLICY_META = {
  niva_aspire: { insurer: 'Niva Bupa', product: 'Aspire', label: 'Niva Bupa — Aspire' },
  hdfc_optima_secure_current: { insurer: 'HDFC ERGO', product: 'Optima Secure', label: 'HDFC ERGO — Optima Secure' },
  hdfc_optima_restore_current: { insurer: 'HDFC ERGO', product: 'Optima Restore', label: 'HDFC ERGO — Optima Restore' },
  hdfc_optima_restore_old: { insurer: 'HDFC ERGO', product: 'Optima Restore (Old)', label: 'HDFC ERGO — Optima Restore (Old)' },
  care_supreme_current: { insurer: 'Care Health', product: 'Care Supreme', label: 'Care Health — Care Supreme' },
  star_comprehensive_current: { insurer: 'Star Health', product: 'Comprehensive', label: 'Star Health — Comprehensive' },
};

export function getPolicyMeta(policyId) {
  return POLICY_META[policyId] || {
    insurer: 'Insurer',
    product: (policyId || '').replace(/_/g, ' '),
    label: (policyId || '').replace(/_/g, ' '),
  };
}

