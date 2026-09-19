export const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    console.error('Copy failed', err);
    return false;
  }
};

export const formatDateGroup = (date: Date) => {
  const today = new Date();
  const diff = (today.getTime() - date.getTime()) / (1000 * 60 * 60 * 24);
  if (diff < 1) return 'Today';
  if (diff < 7) return 'Last 7 days';
  return 'Earlier';
};

export const PROMPT_CHIPS = [
  'Samsung dưới 10tr',
  'Chính sách trả góp',
  'So sánh S24 vs A55',
];
