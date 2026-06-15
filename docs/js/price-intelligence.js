async function loadPriceIntelligence() {
  try {
    const response = await fetch('./data/price-intelligence.json', { cache: 'no-store' });

    if (!response.ok) {
      throw new Error('Price Intelligence adat nem tölthető be.');
    }

    const data = await response.json();

    console.log('Price Intelligence loaded:', data);

  } catch (error) {
    console.warn('Price Intelligence modul hiba:', error.message);
  }
}

loadPriceIntelligence();
