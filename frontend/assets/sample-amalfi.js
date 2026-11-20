// Authentic excerpt from red-hat-examples/pizzeria-amalfi-bank-statement-2025-v6.csv
// (German MT940-style semicolon-delimited CSV with EUR and CHF entries)
export const AMALFI_SAMPLE_FILENAME = "pizzeria-amalfi-sample-2025.csv";
export const AMALFI_DEFAULT_OPENING_EUR = "5000.00";
export const AMALFI_DEFAULT_START_DATE = "2025-06-22";
export const AMALFI_DEFAULT_MOVE_DATE = "2025-06-28";

export const AMALFI_SAMPLE_CSV = [
  '"Account Number";"Booking Date";"Value Date";"Transaction Type";"Payment Reference";"Beneficiary/Payer";"Counterparty Account";"Bank Code";"Amount";"Currency";"Info"',
  '"DE89370400440532013000";"05.07.25";"05.07.25";"CARD SETTLEMENT (DEBIT)";"Daily Debit Card Revenue Settlement Pizzeria Amalfi 05.07.25";"Pizzeria Amalfi Customers (Debit)";"DE92500500000959561143";"HELADEFFXXX";"457,56";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"05.07.25";"05.07.25";"GIRO CARD PAYMENT";"Wholesale Market Fresh Produce Purchase 05.07.25";"Central Wholesale Market";"";"";"-220,03";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"05.07.25";"05.07.25";"SUPPLIER PAYMENT";"Invoice AS-89243 Food & Italian Ingredients Delivery";"Asimex Wholesale Ltd";"DE33500105170011223344";"COBADEFFXXX";"-605,60";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"04.07.25";"04.07.25";"CARD SETTLEMENT (DEBIT)";"Daily Debit Card Revenue Settlement Pizzeria Amalfi 04.07.25";"Pizzeria Amalfi Customers (Debit)";"DE92500500000959561143";"HELADEFFXXX";"435,94";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"04.07.25";"04.07.25";"CREDIT CARD PAYOUT";"Commerzbank Global Pay Card Settlement Ref-CGP-315881";"Commerzbank Global Pay";"DE62700450500931013781";"COBADEFFBZM";"4161,64";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"04.07.25";"04.07.25";"GIRO CARD PAYMENT";"Wholesale Market Fresh Produce Purchase 04.07.25";"Central Wholesale Market";"";"";"-284,74";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"04.07.25";"04.07.25";"SUPPLIER PAYMENT";"Invoice FLV-41884 Italian Wine & Fine Beverages";"Fattoria La Vino GmbH";"DE66500105170099881122";"WELADEDDXXX";"-774,93";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"03.07.25";"03.07.25";"CARD SETTLEMENT (DEBIT)";"Daily Debit Card Revenue Settlement Pizzeria Amalfi 03.07.25";"Pizzeria Amalfi Customers (Debit)";"DE92500500000959561143";"HELADEFFXXX";"309,22";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"03.07.25";"03.07.25";"GIRO CARD PAYMENT";"Wholesale Market Fresh Produce Purchase 03.07.25";"Central Wholesale Market";"";"";"-232,98";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"03.07.25";"03.07.25";"SUPPLIER PAYMENT";"Invoice AS-51897 Food & Italian Ingredients Delivery";"Asimex Wholesale Ltd";"DE33500105170011223344";"COBADEFFXXX";"-575,31";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"02.07.25";"02.07.25";"CARD SETTLEMENT (DEBIT)";"Daily Debit Card Revenue Settlement Pizzeria Amalfi 02.07.25";"Pizzeria Amalfi Customers (Debit)";"DE92500500000959561143";"HELADEFFXXX";"295,25";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"02.07.25";"02.07.25";"GIRO CARD PAYMENT";"Wholesale Market Fresh Produce Purchase 02.07.25";"Central Wholesale Market";"";"";"-284,32";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"01.07.25";"01.07.25";"RENT PAYMENT";"Pizzeria Commercial Space Rent 07/2025";"Main Street Real Estate GmbH";"DE44500105170099887766";"HELADEFFXXX";"-3800,00";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"01.07.25";"01.07.25";"CARD SETTLEMENT (DEBIT)";"Daily Debit Card Revenue Settlement Pizzeria Amalfi 01.07.25";"Pizzeria Amalfi Customers (Debit)";"DE92500500000959561143";"HELADEFFXXX";"335,52";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"01.07.25";"01.07.25";"CREDIT CARD PAYOUT";"Commerzbank Global Pay Card Settlement Ref-CGP-192936";"Commerzbank Global Pay";"DE62700450500931013781";"COBADEFFBZM";"2624,21";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"01.07.25";"01.07.25";"SUPPLIER PAYMENT";"Invoice AS-83339 Food & Italian Ingredients Delivery";"Asimex Wholesale Ltd";"DE33500105170011223344";"COBADEFFXXX";"-670,50";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"28.06.25";"28.06.25";"SALARY PAYMENT";"Owner Salary Withdrawal Vincenzo Amalfi 06/2025";"Vincenzo Amalfi";"DE12345678901234567890";"COBADEFFXXX";"-3200,00";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"28.06.25";"28.06.25";"SALARY PAYMENT";"Net Salary Yusuf Akcit (Pizza Baker) 06/2025";"Yusuf Akcit";"DE98765432109876543210";"INGDDEFFXXX";"-2350,00";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"28.06.25";"28.06.25";"SALARY PAYMENT";"Net Salary Rosa Pavese (Chef) 06/2025";"Rosa Pavese";"DE55443322115544332211";"PBNKDEFFXXX";"-2100,00";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"28.06.25";"28.06.25";"SALARY PAYMENT";"Net Salary Vanessa Paradi (Waitstaff) 06/2025";"Vanessa Paradi";"DE33221144553322114455";"HYVEDEMMXXX";"-950,00";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"27.06.25";"27.06.25";"DIRECT DEBIT";"Social Security Contributions 06/2025 (Pension, Health, Unemployment)";"Techniker Krankenkasse Social Health Fund";"DE12500500000123456789";"HELADEFFXXX";"-2650,00";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"15.06.25";"15.06.25";"INTERNATIONAL WIRE TRANSFER";"Silent Partnership Capital Tranche 06/12 (4166.67 CHF @ 1.050 EUR/CHF) - Luigi\'s Ristorante";"Luigi Amalfi (Luigi\'s Ristorante Zurich)";"CH9300700110001234567";"UBSWCHZH80A";"-4166,67";"CHF";"Transaction booked"',
  '"DE89370400440532013000";"10.06.25";"10.06.25";"DIRECT DEBIT";"Monthly Energy & Gas Advance Payment 06/2025";"City Energy & Utilities AG";"DE86505400280421420100";"COBADEFFXXX";"-650,00";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"10.06.25";"10.06.25";"TAX OFFICE TRANSFER";"Payroll Wage Tax & Solidarity Surcharge 06/2025 Ref-ST-062025";"Tax Office Frankfurt am Main";"DE45500100600012345678";"GENODEF1FFM";"-880,00";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"10.06.25";"10.06.25";"DIRECT DEBIT";"SEPA Direct Debit Income Tax Prepayment Q2/2025 (Prior Year Profit €30k Basis)";"Tax Office Frankfurt am Main";"DE45500100600012345678";"GENODEF1FFM";"-1150,00";"EUR";"Transaction booked"',
  '"DE89370400440532013000";"01.06.25";"01.06.25";"RENT PAYMENT";"Pizzeria Commercial Space Rent 06/2025";"Main Street Real Estate GmbH";"DE44500105170099887766";"HELADEFFXXX";"-3800,00";"EUR";"Transaction booked"',
].join("\n");
