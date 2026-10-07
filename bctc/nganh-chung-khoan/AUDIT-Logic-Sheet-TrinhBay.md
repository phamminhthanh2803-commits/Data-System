# AUDIT logic sheet trình bày — nguồn: IB&Brokerage_Genea_2Q26.xlsx

Quy ước: `[Tên dòng]` = ô cùng kỳ của dòng đó (cùng sheet); `Sheet![Tên dòng | dòng n]` = sheet khác (n = row_order FiinProX);
`(-1 kỳ)` = kỳ trước; `X 4 kỳ gần nhất` = 4 cột liền trước (TTM); `"chuỗi"` = nhãn lấy từ ô nhãn; `kỳ cột` = năm/quý của cột;
`DATA[metric | dòng n | kỳ cột]` = GETPIVOTDATA trên pivot DATA (cộng mọi mã nếu không có `mã=`); `SốTK[...]` = pivot Số TK mở mới.
Cột đại diện: quý mới nhất (Q2-2026) cho khối quý, 2025 cho khối năm; cột đầu (Q1-2016) chỉ khác ở chỗ chưa đủ 4 kỳ TTM.

## Key ratios — khối NGÀNH (dòng 5–33)

| Dòng | Chỉ tiêu | Logic (đã dịch) | Công thức gốc |
|---|---|---|---|
| 5 | Tỷ lệ tài sản sinh lời | (tiêu đề nhóm) | `` |
| 6 | Tổng dư nợ margin (tỷ) | =FS Industry![Loans (margin)]#43 | `='FS Industry'!BN43` |
| 7 | VCSH | =FS Industry![Owner's equity]#53 | `='FS Industry'!BN53` |
| 8 | Nợ/VCSH | =IFERROR((SUM(FS Industry![Short-term borrowings .. Long-term bonds issued (6 dòng)]))/FS Industry![Owner's equity]#53,"") | `=IFERROR((SUM('FS Industry'!BN47:BN52))/'FS Industry'!BN53,"")` |
| 9 | Margin / VCSH | =IFERROR(FS Industry![Loans (margin)]#43/FS Industry![Owner's equity]#53,"") | `=IFERROR('FS Industry'!BN43/'FS Industry'!BN53,"")` |
| 10 | Tỷ lệ đầu tư OTC/VCSH | =IFERROR((FS Industry![Held-to-maturity investments (HTM)]#42+FS Industry![Available-for-sale assets (AFS)]#44)/FS Industry![Owner's equity]#53,"") | `=IFERROR(('FS Industry'!BN42+'FS Industry'!BN44)/'FS Industry'!BN53,"")` |
| 11 | Trái phiếu/VCSH | =IFERROR((FS Industry![Bonds]#80+FS Industry![Bonds]#87+FS Industry![Bonds]#94)/FS Industry![Owner's equity]#53,"") | `=IFERROR(('FS Industry'!BN80+'FS Industry'!BN87+'FS Industry'!BN94)/'FS Industry'!BN53,"")` |
| 13 | Hiệu quả hoạt động | (tiêu đề nhóm) | `` |
| 14 | Margin / Tổng TS | =IFERROR(FS Industry![Loans (margin)]#43/FS Industry![Total assets]#38,"") | `=IFERROR('FS Industry'!BN43/'FS Industry'!BN38,"")` |
| 15 | CIR (TTM) | =IFERROR(-(SUM(FS Industry![Selling expenses]#28 4 kỳ gần nhất)+SUM(FS Industry![Administration]#29 4 kỳ gần nhất))/(SUM(FS Industry![Operating profit]#17 4 kỳ gần nhất)+SUM(FS Industry![Dividends & deposit interest]#25 4 kỳ gần nhất)+SUM(FS Industry![Interest expense]#27 4 kỳ gần nhất)),"") | `=IFERROR(-(SUM('FS Industry'!BK28:BN28)+SUM('FS Industry'!BK29:BN29))/(SUM('FS Industry'!BK17:BN17)+SUM('FS Industry'!BK25:BN25)+SUM('FS Industry'!BK27:BN27)),"")` |
| 16 | ROE (TTM) | =IFERROR(SUM(FS Industry![Net income]#33 4 kỳ gần nhất)/FS Industry![Owner's equity]#53,"") | `=IFERROR(SUM('FS Industry'!BK33:BN33)/'FS Industry'!BN53,"")` |
| 17 | ROA (TTM) | =IFERROR(SUM(FS Industry![Net income]#33 4 kỳ gần nhất)/FS Industry![Total assets]#38,"") | `=IFERROR(SUM('FS Industry'!BK33:BN33)/'FS Industry'!BN38,"")` |
| 18 | Biên LNST (TTM) | =IFERROR(SUM(FS Industry![Net income]#33 4 kỳ gần nhất)/SUM(FS Industry![Revenue]#5 4 kỳ gần nhất),"") | `=IFERROR(SUM('FS Industry'!BK33:BN33)/SUM('FS Industry'!BK5:BN5),"")` |
| 20 | Hiệu quả sinh lời | (tiêu đề nhóm) | `` |
| 21 | Yield FVTPL (Q, quy năm) | =IFERROR(4*(IS![Lãi từ các tài sản tài chính ghi nhận thông qua lãi/lỗ ( FVTPL) \| dòng 2]#9+IS![Lỗ các tài sản tài chính ghi nhận thông qua lãi lỗ (FVTPL) \| dòng 23]#30)/AVERAGE(FS Industry![Financial assets at FVTPL]#41,FS Industry![Financial assets at FVTPL]#41(-1 kỳ)),"") | `=IFERROR(4*(IS!CO9+IS!CO30)/AVERAGE('FS Industry'!BN41,'FS Industry'!BM41),"")` |
| 22 | Yield AFS (Q, quy năm) | =IFERROR(4*(IS![Lãi từ các tài sản tài chính sẵn sàng để bán \| dòng 8]#15+IS![Lỗ và ghi nhận chênh lệch đánh giá theo giá trị hợp lý tài sản tài chính sẵn sàng để bán (AFS) khi phân loại lại \| dòng 29]#36)/AVERAGE(FS Industry![Available-for-sale assets (AFS)]#44,FS Industry![Available-for-sale assets (AFS)]#44(-1 kỳ)),"") | `=IFERROR(4*(IS!CO15+IS!CO36)/AVERAGE('FS Industry'!BN44,'FS Industry'!BM44),"")` |
| 23 | Yield HTM (Q, quy năm) | =IFERROR(4*(IS![Lãi từ các khoản đầu tư nắm giữ đến ngày đáo hạn \| dòng 6]#13+IS![Lỗ các khoản đầu tư nắm giữ đến ngày đáo hạn (HTM) \| dòng 27]#34)/AVERAGE(FS Industry![Held-to-maturity investments (HTM)]#42,FS Industry![Held-to-maturity investments (HTM)]#42(-1 kỳ)),"") | `=IFERROR(4*(IS!CO13+IS!CO34)/AVERAGE('FS Industry'!BN42,'FS Industry'!BM42),"")` |
| 24 | Yield cho vay margin (Q, quy năm) | =IFERROR(4*(IS![Lãi từ các khoản cho vay và phải thu \| dòng 7]#14+IS![Chi phí lãi vay, lỗ từ các khoản cho vay và phải thu (Trước năm 2016) \| dòng 28]#35)/AVERAGE(FS Industry![Loans (margin)]#43,FS Industry![Loans (margin)]#43(-1 kỳ)),"") | `=IFERROR(4*(IS!CO14+IS!CO35)/AVERAGE('FS Industry'!BN43,'FS Industry'!BM43),"")` |
| 25 | Earning yield (Q, quy năm) | =IFERROR(4*(FS Industry![Net Interest income]#35-FS Industry![Interest expense]#27)/AVERAGE(SUM(FS Industry![Financial assets at FVTPL .. Available-for-sale assets (AFS) (4 dòng)]),SUM(FS Industry![Financial assets at FVTPL .. Available-for-sale assets (AFS) (4 dòng)])),"") | `=IFERROR(4*('FS Industry'!BN35-'FS Industry'!BN27)/AVERAGE(SUM('FS Industry'!BN41:BN44),SUM('FS Industry'!BM41:BM44)),"")` |
| 26 | COF (Q, quy năm) | =IFERROR(-4*FS Industry![Interest expense]#27/AVERAGE(SUM(FS Industry![Short-term borrowings .. Long-term bonds issued (6 dòng)]),SUM(FS Industry![Short-term borrowings .. Long-term bonds issued (6 dòng)])),"") | `=IFERROR(-4*'FS Industry'!BN27/AVERAGE(SUM('FS Industry'!BN47:BN52),SUM('FS Industry'!BM47:BM52)),"")` |
| 27 | Spread (Q, quy năm) | =IFERROR([Earning yield (Q, quy năm)]#25-[COF (Q, quy năm)]#26,"") | `=IFERROR(AX25-AX26,"")` |
| 28 | NIM (Q, quy năm) | =4*FS Industry![Net Interest income]#35/AVERAGE(FS Industry![Financial assets at FVTPL]#41+FS Industry![Held-to-maturity investments (HTM)]#42+FS Industry![Loans (margin)]#43+FS Industry![Available-for-sale assets (AFS)]#44,FS Industry![Available-for-sale assets (AFS)]#44(-1 kỳ)+FS Industry![Loans (margin)]#43(-1 kỳ)+FS Industry![Held-to-maturity investments (HTM)]#42(-1 kỳ)+FS Industry![Financial assets at FVTPL]#41(-1 kỳ)) | `=4*'FS Industry'!BN35/AVERAGE('FS Industry'!BN41+'FS Industry'!BN42+'FS Industry'!BN43+'FS Industry'!BN44,'FS Industry'!BM44+'FS Industry'!BM43+'FS Industry'!BM42+'FS Industry'!BM41)` |
| 30 | Cơ cấu tài sản sinh lời | (tiêu đề nhóm) | `` |
| 31 | Margin / IEA | =IFERROR(FS Industry![Loans (margin)]#43/SUM(FS Industry![Financial assets at FVTPL .. Available-for-sale assets (AFS) (4 dòng)]),"") | `=IFERROR('FS Industry'!BN43/SUM('FS Industry'!BN$41:BN$44),"")` |
| 32 | Fixed income / IEA | =IFERROR([Fixed income ngành (Trái phiếu + Tiền gửi + CCTT tiền tệ)]#164/SUM(FS Industry![Financial assets at FVTPL .. Available-for-sale assets (AFS) (4 dòng)]),"") | `=IFERROR(AX164/SUM('FS Industry'!BN$41:BN$44),"")` |
| 33 | Equity / IEA | =IFERROR([Equity ngành (CP niêm yết + chưa NY + CCQ)]#165/SUM(FS Industry![Financial assets at FVTPL .. Available-for-sale assets (AFS) (4 dòng)]),"") | `=IFERROR(AX165/SUM('FS Industry'!BN$41:BN$44),"")` |

## Key ratios — khối CÔNG TY chọn tại G36 (dòng 37–64)

| Dòng | Chỉ tiêu | Logic (đã dịch) | Công thức gốc |
|---|---|---|---|
| 37 | Tỷ lệ tài sản sinh lời | (tiêu đề nhóm) | `` |
| 38 | Tổng dư nợ margin (tỷ) | =[Cho vay margin]#93 | `=AX93` |
| 39 | VCSH | =[Vốn chủ sở hữu]#96 | `=AX96` |
| 40 | Nợ/VCSH | =IFERROR(([Tổng tài sản]#95-[Vốn chủ sở hữu]#96)/[Vốn chủ sở hữu]#96,"") | `=IFERROR((AX95-AX96)/AX96,"")` |
| 41 | Margin / VCSH | =IFERROR([Cho vay margin]#93/[Vốn chủ sở hữu]#96,"") | `=IFERROR(AX93/AX96,"")` |
| 42 | Tỷ lệ đầu tư OTC/VCSH | =IFERROR(([HTM]#92+[AFS]#94)/[Vốn chủ sở hữu]#96,"") | `=IFERROR((AX92+AX94)/AX96,"")` |
| 43 | Trái phiếu/VCSH | =IFERROR([Trái phiếu đầu tư]#123/[Vốn chủ sở hữu]#96,"") | `=IFERROR(AX123/AX96,"")` |
| 45 | Hiệu quả hoạt động | (tiêu đề nhóm) | `` |
| 46 | Margin / Tổng TS | =IFERROR([Cho vay margin]#93/[Tổng tài sản]#95,"") | `=IFERROR(AX93/AX95,"")` |
| 47 | CIR (TTM) | =IFERROR(-SUM([Chi phí bán hàng + quản lý]#129 4 kỳ gần nhất)/SUM([Tổng thu nhập HĐ kiểu NH (TOI = DTHĐ − CP HĐKD + Cổ tức/lãi TG − CP lãi vay)]#131 4 kỳ gần nhất),"") | `=IFERROR(-SUM(AU129:AX129)/SUM(AU131:AX131),"")` |
| 48 | ROE (TTM) | =IFERROR(SUM([LNST]#120 4 kỳ gần nhất)/[Vốn chủ sở hữu]#96,"") | `=IFERROR(SUM(AU120:AX120)/AX96,"")` |
| 49 | ROA (TTM) | =IFERROR(SUM([LNST]#120 4 kỳ gần nhất)/[Tổng tài sản]#95,"") | `=IFERROR(SUM(AU120:AX120)/AX95,"")` |
| 50 | Biên LNST (TTM) | =IFERROR(SUM([LNST]#120 4 kỳ gần nhất)/SUM([Doanh thu hoạt động]#106 4 kỳ gần nhất),"") | `=IFERROR(SUM(AU120:AX120)/SUM(AU106:AX106),"")` |
| 52 | Hiệu quả sinh lời | (tiêu đề nhóm) | `` |
| 53 | Yield FVTPL (TTM) | =IFERROR(SUM([Thu nhập FVTPL]#124 4 kỳ gần nhất)/(([FVTPL]#91+IF(ISNUMBER([FVTPL]#91(-4 kỳ)),[FVTPL]#91(-4 kỳ),[FVTPL]#91))/2),"") | `=IFERROR(SUM(AU124:AX124)/((AX91+IF(ISNUMBER(AT91),AT91,AX91))/2),"")` |
| 54 | Yield AFS (TTM) | =IFERROR(SUM([Thu nhập AFS]#125 4 kỳ gần nhất)/(([AFS]#94+IF(ISNUMBER([AFS]#94(-4 kỳ)),[AFS]#94(-4 kỳ),[AFS]#94))/2),"") | `=IFERROR(SUM(AU125:AX125)/((AX94+IF(ISNUMBER(AT94),AT94,AX94))/2),"")` |
| 55 | Yield HTM (TTM) | =IFERROR(SUM([Thu nhập HTM]#126 4 kỳ gần nhất)/(([HTM]#92+IF(ISNUMBER([HTM]#92(-4 kỳ)),[HTM]#92(-4 kỳ),[HTM]#92))/2),"") | `=IFERROR(SUM(AU126:AX126)/((AX92+IF(ISNUMBER(AT92),AT92,AX92))/2),"")` |
| 56 | Yield cho vay margin (TTM) | =IFERROR(SUM([Thu nhập cho vay]#127 4 kỳ gần nhất)/(([Cho vay margin]#93+IF(ISNUMBER([Cho vay margin]#93(-4 kỳ)),[Cho vay margin]#93(-4 kỳ),[Cho vay margin]#93))/2),"") | `=IFERROR(SUM(AU127:AX127)/((AX93+IF(ISNUMBER(AT93),AT93,AX93))/2),"")` |
| 57 | Earning yield (TTM) | =IFERROR(SUM([Tổng thu nhập TS sinh lời]#128 4 kỳ gần nhất)/(SUM([Tài sản sinh lời (FVTPL+HTM+Margin+AFS)]#121 4 kỳ gần nhất)/4),"") | `=IFERROR(SUM(AU128:AX128)/(SUM(AU121:AX121)/4),"")` |
| 58 | COF (TTM) | =IFERROR(-SUM([Chi phí lãi vay]#116 4 kỳ gần nhất)/(SUM([Tổng nợ vay]#122 4 kỳ gần nhất)/4),"") | `=IFERROR(-SUM(AU116:AX116)/(SUM(AU122:AX122)/4),"")` |
| 59 | NIM (TTM) | =IFERROR([Earning yield (TTM)]#57-[COF (TTM)]#58,"") | `=IFERROR(AX57-AX58,"")` |
| 61 | Cơ cấu tài sản sinh lời | (tiêu đề nhóm) | `` |
| 62 | Margin / IEA | =IFERROR([Cho vay margin]#93/[Tài sản sinh lời (FVTPL+HTM+Margin+AFS)]#121,"") | `=IFERROR(AX93/AX121,"")` |
| 63 | Fixed income / IEA | =IFERROR([Fixed income (Trái phiếu + Tiền gửi + CCTT tiền tệ)]#144/[Tài sản sinh lời (FVTPL+HTM+Margin+AFS)]#121,"") | `=IFERROR(AX144/AX121,"")` |
| 64 | Equity / IEA | =IFERROR([Equity (CP niêm yết + chưa NY + CCQ)]#145/[Tài sản sinh lời (FVTPL+HTM+Margin+AFS)]#121,"") | `=IFERROR(AX145/AX121,"")` |

## Key ratios — khối SỐ LIỆU GỐC của công ty chọn + dòng ngành 147–165 (dòng 88–165)

| Dòng | Chỉ tiêu | Logic (đã dịch) | Công thức gốc |
|---|---|---|---|
| 88 | Kỳ | =kỳ cột | `=AX$36` |
| 89 | Năm | =RIGHT([Kỳ]#88,4)+0 | `=RIGHT(AX$88,4)+0` |
| 90 | Quý | =MID([Kỳ]#88,2,1)+0 | `=MID(AX$88,2,1)+0` |
| 91 | FVTPL | =IFERROR(DATA[mã="VCBS";"Các tài sản tài chính ghi nhận thông qua lãi lỗ (FVTPL)"\| dòng"6"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D91,"metric",$E91,"year",AX$89,"quarter",AX$90),"")` |
| 92 | HTM | =IFERROR(DATA[mã="VCBS";"Các khoản đầu tư nắm giữ đến ngày đáo hạn (HTM)"\| dòng"7"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D92,"metric",$E92,"year",AX$89,"quarter",AX$90),"")` |
| 93 | Cho vay margin | =IFERROR(DATA[mã="VCBS";"Các khoản cho vay"\| dòng"8"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D93,"metric",$E93,"year",AX$89,"quarter",AX$90),"")` |
| 94 | AFS | =IFERROR(DATA[mã="VCBS";"Các khoản tài chính sẵn sàng để bán (AFS)"\| dòng"9"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D94,"metric",$E94,"year",AX$89,"quarter",AX$90),"")` |
| 95 | Tổng tài sản | =IFERROR(DATA[mã="VCBS";"TỔNG CỘNG TÀI SẢN"\| dòng"92"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D95,"metric",$E95,"year",AX$89,"quarter",AX$90),"")` |
| 96 | Vốn chủ sở hữu | =IFERROR(DATA[mã="VCBS";"VỐN CHỦ SỞ HỮU"\| dòng"142"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D96,"metric",$E96,"year",AX$89,"quarter",AX$90),"")` |
| 97 | Vay & nợ thuê TC ngắn hạn | =IFERROR(DATA[mã="VCBS";"Vay và nợ thuê tài sản tài chính ngắn hạn"\| dòng"95"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D97,"metric",$E97,"year",AX$89,"quarter",AX$90),"")` |
| 98 | TP chuyển đổi NH | =IFERROR(DATA[mã="VCBS";"Trái phiếu chuyển đổi ngắn hạn - Cấu phần nợ"\| dòng"99"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D98,"metric",$E98,"year",AX$89,"quarter",AX$90),"")` |
| 99 | TP phát hành NH | =IFERROR(DATA[mã="VCBS";"Trái phiếu phát hành ngắn hạn"\| dòng"100"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D99,"metric",$E99,"year",AX$89,"quarter",AX$90),"")` |
| 100 | Vay & nợ thuê TC dài hạn | =IFERROR(DATA[mã="VCBS";"Vay và nợ thuê tài sản tài chính dài hạn"\| dòng"122"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D100,"metric",$E100,"year",AX$89,"quarter",AX$90),"")` |
| 101 | TP chuyển đổi DH | =IFERROR(DATA[mã="VCBS";"Trái phiếu chuyển đổi dài hạn - Cấu phần nợ"\| dòng"126"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D101,"metric",$E101,"year",AX$89,"quarter",AX$90),"")` |
| 102 | TP phát hành DH | =IFERROR(DATA[mã="VCBS";"Trái phiếu phát hành dài hạn"\| dòng"127"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D102,"metric",$E102,"year",AX$89,"quarter",AX$90),"")` |
| 103 | Trái phiếu đầu tư (1) | =IFERROR(DATA[mã="VCBS";"Trái phiếu"\| dòng"125"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D103,"metric",$E103,"year",AX$89,"quarter",AX$90),"")` |
| 104 | Trái phiếu đầu tư (2) | =IFERROR(DATA[mã="VCBS";"Trái phiếu"\| dòng"138"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D104,"metric",$E104,"year",AX$89,"quarter",AX$90),"")` |
| 105 | Trái phiếu đầu tư (3) | =IFERROR(DATA[mã="VCBS";"Trái phiếu"\| dòng"150"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D105,"metric",$E105,"year",AX$89,"quarter",AX$90),"")` |
| 106 | Doanh thu hoạt động | =IFERROR(DATA[mã="VCBS";"DOANH THU HOẠT ĐỘNG"\| dòng"1"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D106,"metric",$E106,"year",AX$89,"quarter",AX$90),"")` |
| 107 | Lãi FVTPL | =IFERROR(DATA[mã="VCBS";"Lãi từ các tài sản tài chính ghi nhận thông qua lãi/lỗ ( FVTPL)"\| dòng"2"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D107,"metric",$E107,"year",AX$89,"quarter",AX$90),"")` |
| 108 | Lãi HTM | =IFERROR(DATA[mã="VCBS";"Lãi từ các khoản đầu tư nắm giữ đến ngày đáo hạn"\| dòng"6"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D108,"metric",$E108,"year",AX$89,"quarter",AX$90),"")` |
| 109 | Lãi cho vay & phải thu | =IFERROR(DATA[mã="VCBS";"Lãi từ các khoản cho vay và phải thu"\| dòng"7"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D109,"metric",$E109,"year",AX$89,"quarter",AX$90),"")` |
| 110 | Lãi AFS | =IFERROR(DATA[mã="VCBS";"Lãi từ các tài sản tài chính sẵn sàng để bán"\| dòng"8"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D110,"metric",$E110,"year",AX$89,"quarter",AX$90),"")` |
| 111 | Lỗ FVTPL | =IFERROR(DATA[mã="VCBS";"Lỗ các tài sản tài chính ghi nhận thông qua lãi lỗ (FVTPL)"\| dòng"23"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D111,"metric",$E111,"year",AX$89,"quarter",AX$90),"")` |
| 112 | Lỗ HTM | =IFERROR(DATA[mã="VCBS";"Lỗ các khoản đầu tư nắm giữ đến ngày đáo hạn (HTM)"\| dòng"27"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D112,"metric",$E112,"year",AX$89,"quarter",AX$90),"")` |
| 113 | Lỗ cho vay | =IFERROR(DATA[mã="VCBS";"Chi phí lãi vay, lỗ từ các khoản cho vay và phải thu (Trước năm 2016)"\| dòng"28"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D113,"metric",$E113,"year",AX$89,"quarter",AX$90),"")` |
| 114 | Lỗ AFS | =IFERROR(DATA[mã="VCBS";"Lỗ và ghi nhận chênh lệch đánh giá theo giá trị hợp lý tài sản tài chính sẵn sàng để bán (AFS) khi phân loại lại"\| dòng"29"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D114,"metric",$E114,"year",AX$89,"quarter",AX$90),"")` |
| 115 | Chi phí hoạt động kinh doanh | =IFERROR(DATA[mã="VCBS";"Chi phí hoạt động kinh doanh"\| dòng"41"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D115,"metric",$E115,"year",AX$89,"quarter",AX$90),"")` |
| 116 | Chi phí lãi vay | =IFERROR(DATA[mã="VCBS";"Chi phí lãi vay"\| dòng"51"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D116,"metric",$E116,"year",AX$89,"quarter",AX$90),"")` |
| 117 | Cổ tức, lãi tiền gửi | =IFERROR(DATA[mã="VCBS";"Doanh thu, dự thu cổ tức, lãi tiền gửi không cố định phát sinh trong kỳ"\| dòng"45"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D117,"metric",$E117,"year",AX$89,"quarter",AX$90),"")` |
| 118 | Chi phí bán hàng | =IFERROR(DATA[mã="VCBS";"CHI PHÍ BÁN HÀNG"\| dòng"57"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D118,"metric",$E118,"year",AX$89,"quarter",AX$90),"")` |
| 119 | Chi phí quản lý CTCK | =IFERROR(DATA[mã="VCBS";"CHI PHÍ QUẢN LÝ CÔNG TY CHỨNG KHOÁN"\| dòng"58"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D119,"metric",$E119,"year",AX$89,"quarter",AX$90),"")` |
| 120 | LNST | =IFERROR(DATA[mã="VCBS";"Lợi nhuận sau thuế phân bổ cho chủ sở hữu"\| dòng"72"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D120,"metric",$E120,"year",AX$89,"quarter",AX$90),"")` |
| 121 | Tài sản sinh lời (FVTPL+HTM+Margin+AFS) | =SUM([FVTPL .. AFS (4 dòng)]) | `=SUM(AX91:AX94)` |
| 122 | Tổng nợ vay | =SUM([Vay & nợ thuê TC ngắn hạn .. TP phát hành DH (6 dòng)]) | `=SUM(AX97:AX102)` |
| 123 | Trái phiếu đầu tư | =SUM([Trái phiếu đầu tư (1) .. Trái phiếu đầu tư (3) (3 dòng)]) | `=SUM(AX103:AX105)` |
| 124 | Thu nhập FVTPL | =SUM([Lãi FVTPL]#107,[Lỗ FVTPL]#111) | `=SUM(AX107,AX111)` |
| 125 | Thu nhập AFS | =SUM([Lãi AFS]#110,[Lỗ AFS]#114) | `=SUM(AX110,AX114)` |
| 126 | Thu nhập HTM | =SUM([Lãi HTM]#108,[Lỗ HTM]#112) | `=SUM(AX108,AX112)` |
| 127 | Thu nhập cho vay | =SUM([Lãi cho vay & phải thu]#109,[Lỗ cho vay]#113) | `=SUM(AX109,AX113)` |
| 128 | Tổng thu nhập TS sinh lời | =SUM([Thu nhập FVTPL .. Thu nhập cho vay (4 dòng)]) | `=SUM(AX124:AX127)` |
| 129 | Chi phí bán hàng + quản lý | =SUM([Chi phí bán hàng .. Chi phí quản lý CTCK (2 dòng)]) | `=SUM(AX118:AX119)` |
| 130 | Thu nhập hoạt động thuần (DTHĐ − CP HĐKD) | =SUM([Doanh thu hoạt động]#106,[Chi phí hoạt động kinh doanh]#115) | `=SUM(AX106,AX115)` |
| 131 | Tổng thu nhập HĐ kiểu NH (TOI = DTHĐ − CP HĐKD + Cổ tức/lãi TG − CP lãi vay) | =SUM([Doanh thu hoạt động]#106,[Chi phí hoạt động kinh doanh]#115,[Chi phí lãi vay]#116,[Cổ tức, lãi tiền gửi]#117) | `=SUM(AX106,AX115,AX116,AX117)` |
| 132 | CP niêm yết (FVTPL) | =IFERROR(DATA[mã="VCBS";"Cổ phiếu niêm yết"\| dòng"122"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D132,"metric",$E132,"year",AX$89,"quarter",AX$90),"")` |
| 133 | CP chưa niêm yết (FVTPL) | =IFERROR(DATA[mã="VCBS";"Cổ phiếu chưa niêm yết"\| dòng"123"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D133,"metric",$E133,"year",AX$89,"quarter",AX$90),"")` |
| 134 | Chứng chỉ quỹ (FVTPL) | =IFERROR(DATA[mã="VCBS";"Chứng chỉ quỹ"\| dòng"124"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D134,"metric",$E134,"year",AX$89,"quarter",AX$90),"")` |
| 135 | Công cụ TT tiền tệ (FVTPL) | =IFERROR(DATA[mã="VCBS";"Công cụ thị trường tiền tệ"\| dòng"127"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D135,"metric",$E135,"year",AX$89,"quarter",AX$90),"")` |
| 136 | CP niêm yết (AFS) | =IFERROR(DATA[mã="VCBS";"Cổ phiếu niêm yết"\| dòng"135"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D136,"metric",$E136,"year",AX$89,"quarter",AX$90),"")` |
| 137 | CP chưa niêm yết (AFS) | =IFERROR(DATA[mã="VCBS";"Cổ phiếu chưa niêm yết"\| dòng"136"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D137,"metric",$E137,"year",AX$89,"quarter",AX$90),"")` |
| 138 | Chứng chỉ quỹ (AFS) | =IFERROR(DATA[mã="VCBS";"Chứng chỉ quỹ"\| dòng"137"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D138,"metric",$E138,"year",AX$89,"quarter",AX$90),"")` |
| 139 | Công cụ TT tiền tệ (AFS) | =IFERROR(DATA[mã="VCBS";"Công cụ thị trường tiền tệ"\| dòng"139"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D139,"metric",$E139,"year",AX$89,"quarter",AX$90),"")` |
| 140 | Tiền gửi sắp đáo hạn (HTM) | =IFERROR(DATA[mã="VCBS";"Tiền gửi có kỳ hạn sắp đến ngày đáo hạn"\| dòng"147"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D140,"metric",$E140,"year",AX$89,"quarter",AX$90),"")` |
| 141 | Tiền gửi có kỳ hạn (HTM) | =IFERROR(DATA[mã="VCBS";"Tiền gửi có kỳ hạn"\| dòng"148"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D141,"metric",$E141,"year",AX$89,"quarter",AX$90),"")` |
| 142 | Chứng chỉ quỹ (HTM) | =IFERROR(DATA[mã="VCBS";"Chứng chỉ quỹ"\| dòng"149"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D142,"metric",$E142,"year",AX$89,"quarter",AX$90),"")` |
| 143 | Công cụ TT tiền tệ (HTM) | =IFERROR(DATA[mã="VCBS";"Công cụ thị trường tiền tệ"\| dòng"151"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G$36,"row_order",$D143,"metric",$E143,"year",AX$89,"quarter",AX$90),"")` |
| 144 | Fixed income (Trái phiếu + Tiền gửi + CCTT tiền tệ) | =SUM([Trái phiếu đầu tư]#123,[Công cụ TT tiền tệ (FVTPL)]#135,[Công cụ TT tiền tệ (AFS)]#139,[Tiền gửi sắp đáo hạn (HTM)]#140,[Tiền gửi có kỳ hạn (HTM)]#141,[Công cụ TT tiền tệ (HTM)]#143) | `=SUM(AX123,AX135,AX139,AX140,AX141,AX143)` |
| 145 | Equity (CP niêm yết + chưa NY + CCQ) | =SUM([CP niêm yết (FVTPL) .. Chứng chỉ quỹ (FVTPL) (3 dòng)],[CP niêm yết (AFS) .. Chứng chỉ quỹ (AFS) (3 dòng)],[Chứng chỉ quỹ (HTM)]#142) | `=SUM(AX132:AX134,AX136:AX138,AX142)` |
| 147 | DỮ LIỆU GỐC NGÀNH – thuyết minh đầu tư, tổng toàn bộ mã trong pivot DATA (tỷ đồng), không sửa tay | (tiêu đề nhóm) | `` |
| 148 | Chỉ tiêu | (tiêu đề nhóm) | `` |
| 149 | CP niêm yết (FVTPL) – ngành | =IFERROR(DATA["Cổ phiếu niêm yết"\| dòng"122"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"row_order",$D149,"metric",$E149,"year",AX$89,"quarter",AX$90),"")` |
| 150 | CP chưa niêm yết (FVTPL) – ngành | =IFERROR(DATA["Cổ phiếu chưa niêm yết"\| dòng"123"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"row_order",$D150,"metric",$E150,"year",AX$89,"quarter",AX$90),"")` |
| 151 | Chứng chỉ quỹ (FVTPL) – ngành | =IFERROR(DATA["Chứng chỉ quỹ"\| dòng"124"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"row_order",$D151,"metric",$E151,"year",AX$89,"quarter",AX$90),"")` |
| 152 | Công cụ TT tiền tệ (FVTPL) – ngành | =IFERROR(DATA["Công cụ thị trường tiền tệ"\| dòng"127"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"row_order",$D152,"metric",$E152,"year",AX$89,"quarter",AX$90),"")` |
| 153 | CP niêm yết (AFS) – ngành | =IFERROR(DATA["Cổ phiếu niêm yết"\| dòng"135"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"row_order",$D153,"metric",$E153,"year",AX$89,"quarter",AX$90),"")` |
| 154 | CP chưa niêm yết (AFS) – ngành | =IFERROR(DATA["Cổ phiếu chưa niêm yết"\| dòng"136"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"row_order",$D154,"metric",$E154,"year",AX$89,"quarter",AX$90),"")` |
| 155 | Chứng chỉ quỹ (AFS) – ngành | =IFERROR(DATA["Chứng chỉ quỹ"\| dòng"137"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"row_order",$D155,"metric",$E155,"year",AX$89,"quarter",AX$90),"")` |
| 156 | Công cụ TT tiền tệ (AFS) – ngành | =IFERROR(DATA["Công cụ thị trường tiền tệ"\| dòng"139"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"row_order",$D156,"metric",$E156,"year",AX$89,"quarter",AX$90),"")` |
| 157 | Tiền gửi sắp đáo hạn (HTM) – ngành | =IFERROR(DATA["Tiền gửi có kỳ hạn sắp đến ngày đáo hạn"\| dòng"147"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"row_order",$D157,"metric",$E157,"year",AX$89,"quarter",AX$90),"")` |
| 158 | Tiền gửi có kỳ hạn (HTM) – ngành | =IFERROR(DATA["Tiền gửi có kỳ hạn"\| dòng"148"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"row_order",$D158,"metric",$E158,"year",AX$89,"quarter",AX$90),"")` |
| 159 | Chứng chỉ quỹ (HTM) – ngành | =IFERROR(DATA["Chứng chỉ quỹ"\| dòng"149"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"row_order",$D159,"metric",$E159,"year",AX$89,"quarter",AX$90),"")` |
| 160 | Công cụ TT tiền tệ (HTM) – ngành | =IFERROR(DATA["Công cụ thị trường tiền tệ"\| dòng"151"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"row_order",$D160,"metric",$E160,"year",AX$89,"quarter",AX$90),"")` |
| 161 | Trái phiếu đầu tư (1) – ngành | =IFERROR(DATA["Trái phiếu"\| dòng"125"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"row_order",$D161,"metric",$E161,"year",AX$89,"quarter",AX$90),"")` |
| 162 | Trái phiếu đầu tư (2) – ngành | =IFERROR(DATA["Trái phiếu"\| dòng"138"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"row_order",$D162,"metric",$E162,"year",AX$89,"quarter",AX$90),"")` |
| 163 | Trái phiếu đầu tư (3) – ngành | =IFERROR(DATA["Trái phiếu"\| dòng"150"\| kỳ cột],"") | `=IFERROR(GETPIVOTDATA("value",DATA!$A$3,"row_order",$D163,"metric",$E163,"year",AX$89,"quarter",AX$90),"")` |
| 164 | Fixed income ngành (Trái phiếu + Tiền gửi + CCTT tiền tệ) | =SUM([Công cụ TT tiền tệ (FVTPL) – ngành]#152,[Công cụ TT tiền tệ (AFS) – ngành]#156,[Tiền gửi sắp đáo hạn (HTM) – ngành]#157,[Tiền gửi có kỳ hạn (HTM) – ngành]#158,[Công cụ TT tiền tệ (HTM) – ngành]#160,[Trái phiếu đầu tư (1) – ngành .. Trái phiếu đầu tư (3) – ngành (3 dòng)]) | `=SUM(AX152,AX156,AX157,AX158,AX160,AX161:AX163)` |
| 165 | Equity ngành (CP niêm yết + chưa NY + CCQ) | =SUM([CP niêm yết (FVTPL) – ngành .. Chứng chỉ quỹ (FVTPL) – ngành (3 dòng)],[CP niêm yết (AFS) – ngành .. Chứng chỉ quỹ (AFS) – ngành (3 dòng)],[Chứng chỉ quỹ (HTM) – ngành]#159) | `=SUM(AX149:AX151,AX153:AX155,AX159)` |

## FS Industry — khối QUÝ (cột U..BM)

| Dòng | Chỉ tiêu | Logic (đã dịch) | Công thức gốc |
|---|---|---|---|
| 4 | INCOME STATEMENT (IS) | (nhập tay / giá trị) | `Q2-2026` |
| 5 | Revenue | =IS![DOANH THU HOẠT ĐỘNG \| dòng 1]#8 | `=IS!CO8` |
| 6 | Proprietary trading income | =IS![Lãi từ các tài sản tài chính ghi nhận thông qua lãi/lỗ ( FVTPL) \| dòng 2]#9+IS![Lãi từ các khoản đầu tư nắm giữ đến ngày đáo hạn \| dòng 6]#13+IS![Lãi từ các tài sản tài chính sẵn sàng để bán \| dòng 8]#15 | `=IS!CO9+IS!CO13+IS!CO15` |
| 7 | Margin (Rev) | =IS![Lãi từ các khoản cho vay và phải thu \| dòng 7]#14 | `=IS!CO14` |
| 8 | Brokerage income | =IS![Doanh thu nghiệp vụ môi giới chứng khoán \| dòng 10]#17+IS![Doanh thu nghiệp vụ tư vấn đầu tư chứng khoán \| dòng 13]#20 | `=IS!CO17+IS!CO20` |
| 9 | IB | =IS![Doanh thu nghiệp vụ bảo lãnh phát hành chứng khoán \| dòng 11]#18+IS![Doanh thu hoạt động tư vấn tài chính \| dòng 18]#25 | `=IS!CO18+IS!CO25` |
| 10 | Others | =SUM(IS![Lãi từ các công cụ phát sinh phòng ngừa rủi ro \| dòng 9]#16+IS![Tiền gửi của NĐT về giao dịch chứng khoán \| dòng 12]#19+IS![Doanh thu hoạt động ủy thác, đấu giá (Trước năm 2016) \| dòng 14]#21+IS![Doanh thu lưu ký chứng khoán \| dòng 15]#22+IS![Doanh thu hoạt động đầu tư chứng khoán, góp vốn (Trước năm 2016) \| dòng 16]#23+IS![Thu cho thuê sử dụng tài sản (Trước năm 2016) \| dòng 17]#24+IS![Doanh thu khác \| dòng 19]#26) | `=SUM(IS!CO16+IS!CO19+IS!CO21+IS!CO22+IS!CO23+IS!CO24+IS!CO26)` |
| 11 | Operating expenses | =IS![Chi phí hoạt động kinh doanh \| dòng 41]#48 | `=IS!CO48` |
| 12 | Proprietary trading expense | =IS![Lỗ các tài sản tài chính ghi nhận thông qua lãi lỗ (FVTPL) \| dòng 23]#30+IS![Lỗ các khoản đầu tư nắm giữ đến ngày đáo hạn (HTM) \| dòng 27]#34+IS![Lỗ và ghi nhận chênh lệch đánh giá theo giá trị hợp lý tài sản tài chính sẵn sàng để bán (AFS) khi phân loại lại \| dòng 29]#36+IS![Chi phí hoạt động tự doanh \| dòng 32]#39 | `=IS!CO30+IS!CO34+IS!CO36+IS!CO39` |
| 13 | Margin (Exp) | =IS![Chi phí lãi vay, lỗ từ các khoản cho vay và phải thu (Trước năm 2016) \| dòng 28]#35+IS![CP dự phòng TSTC, xử lý tổn thất các khoản phải thu khó đòi là lỗ suy giảm TSTC và CP đi vay \| dòng 30]#37 | `=IS!CO35+IS!CO37` |
| 14 | Brokerage expense | =IS![Chi phí nghiệp vụ môi giới chứng khoán \| dòng 33]#40+IS![Chi phí nghiệp vụ tư vấn đầu tư chứng khoán \| dòng 35]#42 | `=IS!CO40+IS!CO42` |
| 15 | IB expense | =IS![Chi phí nghiệp vụ bảo lãnh, đại lý phát hành chứng khoán \| dòng 34]#41+IS![Chi phí hoạt động tư vấn tài chính \| dòng 38]#45 | `=IS!CO41+IS!CO45` |
| 16 | Others | =IS![Lỗ từ các tài sản tài chính phái sinh phòng ngừa rủi ro \| dòng 31]#38+IS![Chí phí hoạt động đấu giá, ủy thác \| dòng 36]#43+IS![Chi phí nghiệp vụ lưu ký chứng khoán \| dòng 37]#44+IS![Chi phí các dịch vụ khác \| dòng 39]#46 | `=IS!CO38+IS!CO43+IS!CO44+IS!CO46` |
| 17 | Operating profit | =[Revenue]#5+[Operating expenses]#11 | `=BN5+BN11` |
| 18 | Proprietary trading profit | =[Proprietary trading income]#6+[Proprietary trading expense]#12 | `=BN6+BN12` |
| 19 | Margin profit | =[Margin (Rev)]#7+[Margin (Exp)]#13 | `=BN7+BN13` |
| 20 | Brokerage profit | =[Brokerage income]#8+[Brokerage expense]#14 | `=BN8+BN14` |
| 21 | IB profit | =[IB]#9+[IB expense]#15 | `=BN9+BN15` |
| 22 | Others | =[Others]#10+[Others]#16 | `=BN10+BN16` |
| 24 | Finance income | =IS![Doanh thu hoạt động tài chính \| dòng 48]#55 | `=IS!CO55` |
| 25 | Dividends & deposit interest | =IS![Doanh thu, dự thu cổ tức, lãi tiền gửi không cố định phát sinh trong kỳ \| dòng 45]#52 | `=IS!CO52` |
| 26 | Financial expenses | =IS![Chi phí tài chính \| dòng 56]#63 | `=IS!CO63` |
| 27 | Interest expense | =IS![Chi phí lãi vay \| dòng 51]#58 | `=IS!CO58` |
| 28 | Selling expenses | =IS![CHI PHÍ BÁN HÀNG \| dòng 57]#64 | `=IS!CO64` |
| 29 | Administration | =IS![CHI PHÍ QUẢN LÝ CÔNG TY CHỨNG KHOÁN \| dòng 58]#65 | `=IS!CO65` |
| 30 | Operating result | =IS![KẾT QUẢ HOẠT ĐỘNG \| dòng 59]#66 | `=IS!CO66` |
| 31 | Other income & expenses | =IS![Thu nhập khác ròng \| dòng 63]#70 | `=IS!CO70` |
| 32 | PBT | =IS![TỔNG LỢI NHUẬN KẾ TOÁN TRƯỚC THUẾ \| dòng 65]#72 | `=IS!CO72` |
| 33 | Net income | =IS![LỢI NHUẬN KẾ TOÁN SAU THUẾ \| dòng 71]#78 | `=IS!CO78` |
| 35 | Net Interest income | =IS![Lãi từ các tài sản tài chính ghi nhận thông qua lãi/lỗ ( FVTPL) \| dòng 2]#9+IS![Lãi từ các khoản đầu tư nắm giữ đến ngày đáo hạn \| dòng 6]#13+IS![Lãi từ các khoản cho vay và phải thu \| dòng 7]#14+IS![Lãi từ các tài sản tài chính sẵn sàng để bán \| dòng 8]#15+IS![Lỗ các tài sản tài chính ghi nhận thông qua lãi lỗ (FVTPL) \| dòng 23]#30+IS![Lỗ các khoản đầu tư nắm giữ đến ngày đáo hạn (HTM) \| dòng 27]#34+IS![Chi phí lãi vay, lỗ từ các khoản cho vay và phải thu (Trước năm 2016) \| dòng 28]#35+IS![Lỗ và ghi nhận chênh lệch đánh giá theo giá trị hợp lý tài sản tài chính sẵn sàng để bán (AFS) khi phân loại lại \| dòng 29]#36+[Interest expense]#27 | `=IS!CO9+IS!CO13+IS!CO14+IS!CO15+IS!CO30+IS!CO34+IS!CO35+IS!CO36+BN27` |
| 37 | BALANCE SHEET (BS) | =kỳ cột | `=BN$4` |
| 38 | Total assets | =BS![TỔNG CỘNG TÀI SẢN \| dòng 92]#99 | `=BS!CM99` |
| 39 | Short-term financial assets | =BS![Tài sản tài chính ngắn hạn \| dòng 2]#9 | `=BS!CM9` |
| 40 | Cash | =BS![Tiền và tương đương tiền \| dòng 3]#10 | `=BS!CM10` |
| 41 | Financial assets at FVTPL | =BS![Các tài sản tài chính ghi nhận thông qua lãi lỗ (FVTPL) \| dòng 6]#13 | `=BS!CM13` |
| 42 | Held-to-maturity investments (HTM) | =BS![Các khoản đầu tư nắm giữ đến ngày đáo hạn (HTM) \| dòng 7]#14 | `=BS!CM14` |
| 43 | Loans (margin) | =BS![Các khoản cho vay \| dòng 8]#15 | `=BS!CM15` |
| 44 | Available-for-sale assets (AFS) | =BS![Các khoản tài chính sẵn sàng để bán (AFS) \| dòng 9]#16 | `=BS!CM16` |
| 45 | Receivables | =BS![Tổng các khoản phải thu \| dòng 11]#18 | `=BS!CM18` |
| 47 | Short-term borrowings | =BS![Vay và nợ thuê tài sản tài chính ngắn hạn \| dòng 95]#102 | `=BS!CM102` |
| 48 | Short-term convertible bonds | =BS![Trái phiếu chuyển đổi ngắn hạn - Cấu phần nợ \| dòng 99]#106 | `=BS!CM106` |
| 49 | Short-term bonds issued | =BS![Trái phiếu phát hành ngắn hạn \| dòng 100]#107 | `=BS!CM107` |
| 50 | Long-term borrowings | =BS![Vay và nợ thuê tài sản tài chính dài hạn \| dòng 122]#129 | `=BS!CM129` |
| 51 | Long-term convertible bonds | =BS![Trái phiếu chuyển đổi dài hạn - Cấu phần nợ \| dòng 126]#133 | `=BS!CM133` |
| 52 | Long-term bonds issued | =BS![Trái phiếu phát hành dài hạn \| dòng 127]#134 | `=BS!CM134` |
| 53 | Owner's equity | =BS![VỐN CHỦ SỞ HỮU \| dòng 142]#149 | `=BS!CM149` |
| 54 | Paid-in capital | =BS![Vốn góp của chủ sở hữu \| dòng 145]#152 | `=BS!CM152` |
| 55 | Controlling interest | =BS![Vốn chủ sở hữu \| dòng 143]#150-BS![Lợi ích cổ đông không kiểm soát \| dòng 163]#170 | `=BS!CM150-BS!CM170` |
| 59 | NOTES | =kỳ cột | `=BN$4` |
| 60 | Trading value (company) | =NOTE![GIÁ TRỊ GIAO DỊCH THỰC HIỆN TRONG KỲ CỦA CTCK]#107 | `=NOTE!CO107` |
| 61 | Shares (Comp-val) | =NOTE![Giá trị Cổ phiếu]#108 | `=NOTE!CO108` |
| 62 | Bond (Comp-val) | =NOTE![Giá trị Trái phiếu]#109 | `=NOTE!CO109` |
| 63 | Other (Comp-val) | =NOTE![Giá trị chứng khoán khác]#110 | `=NOTE!CO110` |
| 64 | Trading value (investor) | =NOTE![GIÁ TRỊ GIAO DỊCH THỰC HIỆN TRONG KỲ CỦA NĐT]#115 | `=NOTE!CO115` |
| 65 | Shares (Inv-val) | =NOTE![Giá trị Cổ phiếu]#116 | `=NOTE!CO116` |
| 66 | Bond (Inv-val) | =NOTE![Giá trị Trái phiếu]#117 | `=NOTE!CO117` |
| 67 | Other (Inv-val) | =NOTE![Giá trị chứng khoán khác]#118 | `=NOTE!CO118` |
| 68 | Trading volume (company) | =NOTE![KHỐI LƯỢNG GIAO DỊCH THỰC HIỆN TRONG KỲ CỦA CTCK]#103 | `=NOTE!CO103` |
| 69 | Shares (Comp-vol) | =NOTE![Khối lượng Cổ phiếu]#104 | `=NOTE!CO104` |
| 70 | Bond (Comp-vol) | =NOTE![Khối lượng Trái phiếu]#105 | `=NOTE!CO105` |
| 71 | Other (Comp-vol) | =NOTE![Khối lượng chứng khoán khác]#106 | `=NOTE!CO106` |
| 72 | Trading volume (investor) | =NOTE![KHỐI LƯỢNG GIAO DỊCH THỰC HIỆN TRONG KỲ CỦA NĐT]#111 | `=NOTE!CO111` |
| 73 | Shares (Inv-vol) | =NOTE![Khối lượng Cổ phiếu]#112 | `=NOTE!CO112` |
| 74 | Bond (Inv-vol) | =NOTE![Khối lượng Trái phiếu]#113 | `=NOTE!CO113` |
| 75 | Other (Inv-vol) | =NOTE![Khối lượng chứng khoán khác]#114 | `=NOTE!CO114` |
| 76 | FVPTL Portfolio | =NOTE![Giá trị ghi sổ Tài sản tài chính ghi nhận thông qua lãi/lỗ (FVTPL)]#127 | `=NOTE!CO127` |
| 77 | Listed Equity | =NOTE![Cổ phiếu niêm yết]#129 | `=NOTE!CO129` |
| 78 | Unlisted Equity | =NOTE![Cổ phiếu chưa niêm yết]#130 | `=NOTE!CO130` |
| 79 | Fund administration | =NOTE![Chứng chỉ quỹ]#131 | `=NOTE!CO131` |
| 80 | Bonds | =NOTE![Trái phiếu]#132 | `=NOTE!CO132` |
| 81 | CDs | =NOTE![Công cụ thị trường tiền tệ]#134 | `=NOTE!CO134` |
| 82 | Others | =SUM(NOTE![TSTC phái sinh niêm yết .. TSTC khác (6 dòng)]) | `=SUM(NOTE!CO135:CO140)` |
| 83 | AFS Portfolio | =NOTE![Giá trị ghi sổ Tài sản tài chính sẵn sàng để bán (AFS)]#141 | `=NOTE!CO141` |
| 84 | Listed Equity | =NOTE![Cổ phiếu niêm yết]#142 | `=NOTE!CO142` |
| 85 | Unlisted Equity | =NOTE![Cổ phiếu chưa niêm yết]#143 | `=NOTE!CO143` |
| 86 | Fund administration | =NOTE![Chứng chỉ quỹ]#144 | `=NOTE!CO144` |
| 87 | Bonds | =NOTE![Trái phiếu]#145 | `=NOTE!CO145` |
| 88 | CDs | =NOTE![Công cụ thị trường tiền tệ]#146 | `=NOTE!CO146` |
| 89 | Others | =SUM(NOTE![TSTC phái sinh niêm yết .. TSTC khác (6 dòng)]) | `=SUM(NOTE!CO147:CO152)` |
| 90 | HTM Portfolio | =NOTE![Giá trị ghi sổ Các khoản đầu tư giữ đến ngày đáo hạn (HTM)]#153 | `=NOTE!CO153` |
| 91 | Listed Equity | =NOTE![Tiền gửi có kỳ hạn sắp đến ngày đáo hạn]#154 | `=NOTE!CO154` |
| 92 | Unlisted Equity | =NOTE![Tiền gửi có kỳ hạn]#155 | `=NOTE!CO155` |
| 93 | Fund administration | =NOTE![Chứng chỉ quỹ]#156 | `=NOTE!CO156` |
| 94 | Bonds | =NOTE![Trái phiếu]#157 | `=NOTE!CO157` |
| 95 | CDs | =NOTE![Công cụ thị trường tiền tệ]#158 | `=NOTE!CO158` |
| 96 | Others | =SUM(NOTE![TSTC phái sinh niêm yết .. TSTC khác (6 dòng)]) | `=SUM(NOTE!CO159:CO164)` |
| 98 | Long Term Investments | =NOTE![Đầu tư tài chính dài hạn]#239 | `=NOTE!CO239` |
| 99 | AFS | =NOTE![Chứng khoán đầu tư sẵn sàng để bán]#240 | `=NOTE!CO240` |
| 100 | Listed Equity | =NOTE![Cổ phiếu niêm yết]#241 | `=NOTE!CO241` |
| 101 | Unlisted Equity | =NOTE![Cổ phiếu chưa niêm yết]#242 | `=NOTE!CO242` |
| 102 | Fund administration | =NOTE![Chứng chỉ quỹ]#243 | `=NOTE!CO243` |
| 103 | Bonds | =NOTE![Trái phiếu]#244 | `=NOTE!CO244` |
| 104 | HTM | =NOTE![Chứng khoán nắm giữ đến ngày đáo hạn]#245 | `=NOTE!CO245` |
| 105 | Listed Equity | =NOTE![Cổ phiếu niêm yết]#246 | `=NOTE!CO246` |
| 106 | Unlisted Equity | =NOTE![Cổ phiếu chưa niêm yết]#247 | `=NOTE!CO247` |
| 107 | Fund administration | =NOTE![Chứng chỉ quỹ]#248 | `=NOTE!CO248` |
| 108 | Bonds | =NOTE![Trái phiếu]#249 | `=NOTE!CO249` |
| 109 | Subsidiaries | =NOTE![Đầu tư vào công ty con]#250 | `=NOTE!CO250` |
| 110 | JVs | =NOTE![Góp vốn liên doanh, liên kết]#251 | `=NOTE!CO251` |
| 111 | Others | =NOTE![Đầu tư tài chính khác]#252 | `=NOTE!CO252` |
| 113 | Investment impairment | =NOTE![TRÍCH LẬP DỰ PHÒNG GIẢM GIÁ CÁC TÀI SẢN TÀI CHÍNH]#253 | `=NOTE!CO253` |
| 114 | FVPTL | =NOTE![Tài sản tài chính ghi nhận thông qua lãi/lỗ (FVTPL)]#254 | `=NOTE!CO254` |
| 115 | AFS | =NOTE![Tài sản tài chính sẵn sàng để bán (AFS)]#255 | `=NOTE!CO255` |
| 116 | HTM | =NOTE![Các khoản đầu tư giữ đến ngày đáo hạn (HTM)]#256 | `=NOTE!CO256` |
| 117 | Margin | =NOTE![Các khoản cho vay và phải thu]#257 | `=NOTE!CO257` |
| 119 | ST impairment | =NOTE![DỰ PHÒNG GIẢM GIÁ ĐẦU TƯ NGẮN HẠN]#258 | `=NOTE!CO258` |
| 120 | Listed Equity | =NOTE![Cổ phiếu niêm yết]#259 | `=NOTE!CO259` |
| 121 | Unlisted Equity | =NOTE![Cổ phiếu chưa niêm yết]#260 | `=NOTE!CO260` |
| 122 | Fund administration | =NOTE![Chứng chỉ quỹ]#261 | `=NOTE!CO261` |
| 123 | Bonds | =NOTE![Trái phiếu]#262 | `=NOTE!CO262` |
| 124 | Others | =NOTE![Đầu tư khác]#263 | `=NOTE!CO263` |
| 126 | LT impairment | =NOTE![DỰ PHÒNG GIẢM GIÁ ĐẦU TƯ DÀI HẠN]#264 | `=NOTE!CO264` |
| 127 | Listed Equity | =NOTE![Cổ phiếu niêm yết]#265 | `=NOTE!CO265` |
| 128 | Unlisted Equity | =NOTE![Cổ phiếu chưa niêm yết]#266 | `=NOTE!CO266` |
| 129 | Fund administration | =NOTE![Chứng chỉ quỹ]#267 | `=NOTE!CO267` |
| 130 | Bonds | =NOTE![Trái phiếu]#268 | `=NOTE!CO268` |
| 131 | JVs and etc | =NOTE![Đầu tư góp vốn]#269 | `=NOTE!CO269` |
| 132 | Others | =NOTE![Đầu tư khác]#270 | `=NOTE!CO270` |
| 139 | Bonds | =SUMIF([FVPTL Portfolio .. Others (36 dòng)],"Bonds",[FVPTL Portfolio .. Others (36 dòng)]) | `=SUMIF($F$76:$F$111,$F$139,BN76:BN111)` |
| 141 |  | =FS Industry!BM140/[Bonds]#139 | `=BM140/BM139` |

## FS Industry — khối NĂM (cột H..T)

| Dòng | Chỉ tiêu | Logic (đã dịch) | Công thức gốc |
|---|---|---|---|
| 4 | INCOME STATEMENT (IS) | (nhập tay / giá trị) | `2025` |
| 5 | Revenue | =Σ4quý_của_năm_cột([Revenue]#5) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U5:$BM5)` |
| 6 | Proprietary trading income | =Σ4quý_của_năm_cột([Proprietary trading income]#6) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U6:$BM6)` |
| 7 | Margin (Rev) | =Σ4quý_của_năm_cột([Margin (Rev)]#7) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U7:$BM7)` |
| 8 | Brokerage income | =Σ4quý_của_năm_cột([Brokerage income]#8) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U8:$BM8)` |
| 9 | IB | =Σ4quý_của_năm_cột([IB]#9) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U9:$BM9)` |
| 10 | Others | =Σ4quý_của_năm_cột([Others]#10) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U10:$BM10)` |
| 11 | Operating expenses | =Σ4quý_của_năm_cột([Operating expenses]#11) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U11:$BM11)` |
| 12 | Proprietary trading expense | =Σ4quý_của_năm_cột([Proprietary trading expense]#12) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U12:$BM12)` |
| 13 | Margin (Exp) | =Σ4quý_của_năm_cột([Margin (Exp)]#13) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U13:$BM13)` |
| 14 | Brokerage expense | =Σ4quý_của_năm_cột([Brokerage expense]#14) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U14:$BM14)` |
| 15 | IB expense | =Σ4quý_của_năm_cột([IB expense]#15) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U15:$BM15)` |
| 16 | Others | =Σ4quý_của_năm_cột([Others]#16) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U16:$BM16)` |
| 17 | Operating profit | =Σ4quý_của_năm_cột([Operating profit]#17) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U17:$BM17)` |
| 18 | Proprietary trading profit | =Σ4quý_của_năm_cột([Proprietary trading profit]#18) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U18:$BM18)` |
| 19 | Margin profit | =Σ4quý_của_năm_cột([Margin profit]#19) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U19:$BM19)` |
| 20 | Brokerage profit | =Σ4quý_của_năm_cột([Brokerage profit]#20) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U20:$BM20)` |
| 21 | IB profit | =Σ4quý_của_năm_cột([IB profit]#21) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U21:$BM21)` |
| 22 | Others | =Σ4quý_của_năm_cột([Others]#22) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U22:$BM22)` |
| 24 | Finance income | =Σ4quý_của_năm_cột([Finance income]#24) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U24:$BM24)` |
| 25 | Dividends & deposit interest | =Σ4quý_của_năm_cột([Dividends & deposit interest]#25) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U25:$BM25)` |
| 26 | Financial expenses | =Σ4quý_của_năm_cột([Financial expenses]#26) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U26:$BM26)` |
| 27 | Interest expense | =Σ4quý_của_năm_cột([Interest expense]#27) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U27:$BM27)` |
| 28 | Selling expenses | =Σ4quý_của_năm_cột([Selling expenses]#28) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U28:$BM28)` |
| 29 | Administration | =Σ4quý_của_năm_cột([Administration]#29) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U29:$BM29)` |
| 30 | Operating result | =Σ4quý_của_năm_cột([Operating result]#30) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U30:$BM30)` |
| 31 | Other income & expenses | =Σ4quý_của_năm_cột([Other income & expenses]#31) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U31:$BM31)` |
| 32 | PBT | =Σ4quý_của_năm_cột([PBT]#32) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U32:$BM32)` |
| 33 | Net income | =Σ4quý_của_năm_cột([Net income]#33) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U33:$BM33)` |
| 35 | Net Interest income | =Σ4quý_của_năm_cột([Net Interest income]#35) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U35:$BM35)` |
| 37 | BALANCE SHEET (BS) | =kỳ cột | `=R$4` |
| 38 | Total assets | =GiáTrị_Q4_của_năm_cột([Total assets]#38) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U38:$BM38)` |
| 39 | Short-term financial assets | =GiáTrị_Q4_của_năm_cột([Short-term financial assets]#39) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U39:$BM39)` |
| 40 | Cash | =GiáTrị_Q4_của_năm_cột([Cash]#40) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U40:$BM40)` |
| 41 | Financial assets at FVTPL | =GiáTrị_Q4_của_năm_cột([Financial assets at FVTPL]#41) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U41:$BM41)` |
| 42 | Held-to-maturity investments (HTM) | =GiáTrị_Q4_của_năm_cột([Held-to-maturity investments (HTM)]#42) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U42:$BM42)` |
| 43 | Loans (margin) | =GiáTrị_Q4_của_năm_cột([Loans (margin)]#43) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U43:$BM43)` |
| 44 | Available-for-sale assets (AFS) | =GiáTrị_Q4_của_năm_cột([Available-for-sale assets (AFS)]#44) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U44:$BM44)` |
| 45 | Receivables | =GiáTrị_Q4_của_năm_cột([Receivables]#45) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U45:$BM45)` |
| 46 |  | =GiáTrị_Q4_của_năm_cột([46]#46) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U46:$BM46)` |
| 47 | Short-term borrowings | =GiáTrị_Q4_của_năm_cột([Short-term borrowings]#47) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U47:$BM47)` |
| 48 | Short-term convertible bonds | =GiáTrị_Q4_của_năm_cột([Short-term convertible bonds]#48) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U48:$BM48)` |
| 49 | Short-term bonds issued | =GiáTrị_Q4_của_năm_cột([Short-term bonds issued]#49) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U49:$BM49)` |
| 50 | Long-term borrowings | =GiáTrị_Q4_của_năm_cột([Long-term borrowings]#50) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U50:$BM50)` |
| 51 | Long-term convertible bonds | =GiáTrị_Q4_của_năm_cột([Long-term convertible bonds]#51) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U51:$BM51)` |
| 52 | Long-term bonds issued | =GiáTrị_Q4_của_năm_cột([Long-term bonds issued]#52) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U52:$BM52)` |
| 53 | Owner's equity | =GiáTrị_Q4_của_năm_cột([Owner's equity]#53) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U53:$BM53)` |
| 54 | Paid-in capital | =GiáTrị_Q4_của_năm_cột([Paid-in capital]#54) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U54:$BM54)` |
| 55 | Controlling interest | =GiáTrị_Q4_của_năm_cột([Controlling interest]#55) | `=SUMPRODUCT((LEFT($U$4:$BM$4,2)="Q4")*(RIGHT($U$4:$BM$4,4)+0=R$4)*$U55:$BM55)` |
| 59 | NOTES | =kỳ cột | `=R$4` |
| 60 | Trading value (company) | =Σ4quý_của_năm_cột([Trading value (company)]#60) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U60:$BM60)` |
| 61 | Shares (Comp-val) | =Σ4quý_của_năm_cột([Shares (Comp-val)]#61) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U61:$BM61)` |
| 62 | Bond (Comp-val) | =Σ4quý_của_năm_cột([Bond (Comp-val)]#62) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U62:$BM62)` |
| 63 | Other (Comp-val) | =Σ4quý_của_năm_cột([Other (Comp-val)]#63) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U63:$BM63)` |
| 64 | Trading value (investor) | =Σ4quý_của_năm_cột([Trading value (investor)]#64) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U64:$BM64)` |
| 65 | Shares (Inv-val) | =Σ4quý_của_năm_cột([Shares (Inv-val)]#65) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U65:$BM65)` |
| 66 | Bond (Inv-val) | =Σ4quý_của_năm_cột([Bond (Inv-val)]#66) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U66:$BM66)` |
| 67 | Other (Inv-val) | =Σ4quý_của_năm_cột([Other (Inv-val)]#67) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U67:$BM67)` |
| 68 | Trading volume (company) | =Σ4quý_của_năm_cột([Trading volume (company)]#68) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U68:$BM68)` |
| 69 | Shares (Comp-vol) | =Σ4quý_của_năm_cột([Shares (Comp-vol)]#69) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U69:$BM69)` |
| 70 | Bond (Comp-vol) | =Σ4quý_của_năm_cột([Bond (Comp-vol)]#70) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U70:$BM70)` |
| 71 | Other (Comp-vol) | =Σ4quý_của_năm_cột([Other (Comp-vol)]#71) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U71:$BM71)` |
| 72 | Trading volume (investor) | =Σ4quý_của_năm_cột([Trading volume (investor)]#72) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U72:$BM72)` |
| 73 | Shares (Inv-vol) | =Σ4quý_của_năm_cột([Shares (Inv-vol)]#73) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U73:$BM73)` |
| 74 | Bond (Inv-vol) | =Σ4quý_của_năm_cột([Bond (Inv-vol)]#74) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U74:$BM74)` |
| 75 | Other (Inv-vol) | =Σ4quý_của_năm_cột([Other (Inv-vol)]#75) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U75:$BM75)` |
| 76 | FVPTL Portfolio | =Σ4quý_của_năm_cột([FVPTL Portfolio]#76) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U76:$BM76)` |
| 77 | Listed Equity | =Σ4quý_của_năm_cột([Listed Equity]#77) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U77:$BM77)` |
| 78 | Unlisted Equity | =Σ4quý_của_năm_cột([Unlisted Equity]#78) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U78:$BM78)` |
| 79 | Fund administration | =Σ4quý_của_năm_cột([Fund administration]#79) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U79:$BM79)` |
| 80 | Bonds | =Σ4quý_của_năm_cột([Bonds]#80) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U80:$BM80)` |
| 81 | CDs | =Σ4quý_của_năm_cột([CDs]#81) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U81:$BM81)` |
| 82 | Others | =Σ4quý_của_năm_cột([Others]#82) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U82:$BM82)` |
| 83 | AFS Portfolio | =Σ4quý_của_năm_cột([AFS Portfolio]#83) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U83:$BM83)` |
| 84 | Listed Equity | =Σ4quý_của_năm_cột([Listed Equity]#84) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U84:$BM84)` |
| 85 | Unlisted Equity | =Σ4quý_của_năm_cột([Unlisted Equity]#85) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U85:$BM85)` |
| 86 | Fund administration | =Σ4quý_của_năm_cột([Fund administration]#86) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U86:$BM86)` |
| 87 | Bonds | =Σ4quý_của_năm_cột([Bonds]#87) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U87:$BM87)` |
| 88 | CDs | =Σ4quý_của_năm_cột([CDs]#88) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U88:$BM88)` |
| 89 | Others | =Σ4quý_của_năm_cột([Others]#89) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U89:$BM89)` |
| 90 | HTM Portfolio | =Σ4quý_của_năm_cột([HTM Portfolio]#90) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U90:$BM90)` |
| 91 | Listed Equity | =Σ4quý_của_năm_cột([Listed Equity]#91) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U91:$BM91)` |
| 92 | Unlisted Equity | =Σ4quý_của_năm_cột([Unlisted Equity]#92) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U92:$BM92)` |
| 93 | Fund administration | =Σ4quý_của_năm_cột([Fund administration]#93) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U93:$BM93)` |
| 94 | Bonds | =Σ4quý_của_năm_cột([Bonds]#94) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U94:$BM94)` |
| 95 | CDs | =Σ4quý_của_năm_cột([CDs]#95) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U95:$BM95)` |
| 96 | Others | =Σ4quý_của_năm_cột([Others]#96) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U96:$BM96)` |
| 98 | Long Term Investments | =Σ4quý_của_năm_cột([Long Term Investments]#98) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U98:$BM98)` |
| 99 | AFS | =Σ4quý_của_năm_cột([AFS]#99) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U99:$BM99)` |
| 100 | Listed Equity | =Σ4quý_của_năm_cột([Listed Equity]#100) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U100:$BM100)` |
| 101 | Unlisted Equity | =Σ4quý_của_năm_cột([Unlisted Equity]#101) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U101:$BM101)` |
| 102 | Fund administration | =Σ4quý_của_năm_cột([Fund administration]#102) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U102:$BM102)` |
| 103 | Bonds | =Σ4quý_của_năm_cột([Bonds]#103) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U103:$BM103)` |
| 104 | HTM | =Σ4quý_của_năm_cột([HTM]#104) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U104:$BM104)` |
| 105 | Listed Equity | =Σ4quý_của_năm_cột([Listed Equity]#105) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U105:$BM105)` |
| 106 | Unlisted Equity | =Σ4quý_của_năm_cột([Unlisted Equity]#106) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U106:$BM106)` |
| 107 | Fund administration | =Σ4quý_của_năm_cột([Fund administration]#107) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U107:$BM107)` |
| 108 | Bonds | =Σ4quý_của_năm_cột([Bonds]#108) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U108:$BM108)` |
| 109 | Subsidiaries | =Σ4quý_của_năm_cột([Subsidiaries]#109) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U109:$BM109)` |
| 110 | JVs | =Σ4quý_của_năm_cột([JVs]#110) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U110:$BM110)` |
| 111 | Others | =Σ4quý_của_năm_cột([Others]#111) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U111:$BM111)` |
| 113 | Investment impairment | =Σ4quý_của_năm_cột([Investment impairment]#113) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U113:$BM113)` |
| 114 | FVPTL | =Σ4quý_của_năm_cột([FVPTL]#114) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U114:$BM114)` |
| 115 | AFS | =Σ4quý_của_năm_cột([AFS]#115) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U115:$BM115)` |
| 116 | HTM | =Σ4quý_của_năm_cột([HTM]#116) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U116:$BM116)` |
| 117 | Margin | =Σ4quý_của_năm_cột([Margin]#117) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U117:$BM117)` |
| 119 | ST impairment | =Σ4quý_của_năm_cột([ST impairment]#119) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U119:$BM119)` |
| 120 | Listed Equity | =Σ4quý_của_năm_cột([Listed Equity]#120) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U120:$BM120)` |
| 121 | Unlisted Equity | =Σ4quý_của_năm_cột([Unlisted Equity]#121) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U121:$BM121)` |
| 122 | Fund administration | =Σ4quý_của_năm_cột([Fund administration]#122) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U122:$BM122)` |
| 123 | Bonds | =Σ4quý_của_năm_cột([Bonds]#123) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U123:$BM123)` |
| 124 | Others | =Σ4quý_của_năm_cột([Others]#124) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U124:$BM124)` |
| 126 | LT impairment | =Σ4quý_của_năm_cột([LT impairment]#126) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U126:$BM126)` |
| 127 | Listed Equity | =Σ4quý_của_năm_cột([Listed Equity]#127) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U127:$BM127)` |
| 128 | Unlisted Equity | =Σ4quý_của_năm_cột([Unlisted Equity]#128) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U128:$BM128)` |
| 129 | Fund administration | =Σ4quý_của_năm_cột([Fund administration]#129) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U129:$BM129)` |
| 130 | Bonds | =Σ4quý_của_năm_cột([Bonds]#130) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U130:$BM130)` |
| 131 | JVs and etc | =Σ4quý_của_năm_cột([JVs and etc]#131) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U131:$BM131)` |
| 132 | Others | =Σ4quý_của_năm_cột([Others]#132) | `=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=R$4)*$U132:$BM132)` |
| 139 | Bonds | =SUMIF([FVPTL Portfolio .. Others (36 dòng)],"Bonds",[FVPTL Portfolio .. Others (36 dòng)]) | `=SUMIF($F$76:$F$111,$F$139,R76:R111)` |

## Drivers

| Dòng | Chỉ tiêu | Logic (đã dịch) | Công thức gốc |
|---|---|---|---|
| 8 | Thị phần môi giới | ="Q"&kỳ cột&"-"&kỳ cột | `="Q"&AP10&"-"&AP9` |
| 9 |  | =IF(kỳ cột-1=4,kỳ cột-1+1,kỳ cột-1) | `=IF(AO10=4,AO9+1,AO9)` |
| 10 |  | =IF(kỳ cột-1=4,1,kỳ cột-1+1) | `=IF(AO10=4,1,AO10+1)` |
| 11 | Công ty ▼ | (tiêu đề nhóm) | `` |
| 12 | SSI | =IFNA(XLOOKUP("SSI"&"\|"&"HOSE"&"\|"&kỳ cột,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"") | `=_xlfn.IFNA(_xlfn.XLOOKUP($F12&"\|"&$G$12&"\|"&AP$8,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"")` |
| 13 | TCX | =IFNA(XLOOKUP("TCX"&"\|"&"HOSE"&"\|"&kỳ cột,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"") | `=_xlfn.IFNA(_xlfn.XLOOKUP($F13&"\|"&$G$12&"\|"&AP$8,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"")` |
| 14 | VCK | =IFNA(XLOOKUP("VCK"&"\|"&"HOSE"&"\|"&kỳ cột,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"") | `=_xlfn.IFNA(_xlfn.XLOOKUP($F14&"\|"&$G$12&"\|"&AP$8,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"")` |
| 15 | VCI | =IFNA(XLOOKUP("VCI"&"\|"&"HOSE"&"\|"&kỳ cột,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"") | `=_xlfn.IFNA(_xlfn.XLOOKUP($F15&"\|"&$G$12&"\|"&AP$8,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"")` |
| 16 | VND | =IFNA(XLOOKUP("VND"&"\|"&"HOSE"&"\|"&kỳ cột,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"") | `=_xlfn.IFNA(_xlfn.XLOOKUP($F16&"\|"&$G$12&"\|"&AP$8,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"")` |
| 17 | VPX | =IFNA(XLOOKUP("VPX"&"\|"&"HOSE"&"\|"&kỳ cột,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"") | `=_xlfn.IFNA(_xlfn.XLOOKUP($F17&"\|"&$G$12&"\|"&AP$8,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"")` |
| 18 | HCM | =IFNA(XLOOKUP("HCM"&"\|"&"HOSE"&"\|"&kỳ cột,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"") | `=_xlfn.IFNA(_xlfn.XLOOKUP($F18&"\|"&$G$12&"\|"&AP$8,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"")` |
| 19 | KIS | =IFNA(XLOOKUP("KIS"&"\|"&"HOSE"&"\|"&kỳ cột,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"") | `=_xlfn.IFNA(_xlfn.XLOOKUP($F19&"\|"&$G$12&"\|"&AP$8,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"")` |
| 20 | MBS | =IFNA(XLOOKUP("MBS"&"\|"&"HOSE"&"\|"&kỳ cột,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"") | `=_xlfn.IFNA(_xlfn.XLOOKUP($F20&"\|"&$G$12&"\|"&AP$8,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"")` |
| 21 | MAS | =IFNA(XLOOKUP("MAS"&"\|"&"HOSE"&"\|"&kỳ cột,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"") | `=_xlfn.IFNA(_xlfn.XLOOKUP($F21&"\|"&$G$12&"\|"&AP$8,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"")` |
| 22 | VCBS | =IFNA(XLOOKUP("VCBS"&"\|"&"HOSE"&"\|"&kỳ cột,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"") | `=_xlfn.IFNA(_xlfn.XLOOKUP($F22&"\|"&$G$12&"\|"&AP$8,tbl_MarketShare[company]&"\|"&tbl_MarketShare[market]&"\|"&tbl_MarketShare[period],tbl_MarketShare[market-share]),"")` |
| 25 | Thanh khoản | (tiêu đề nhóm) | `` |
| 27 | Giá trị giao dịch | (tiêu đề nhóm) | `` |
| 28 | HOSE | =[1]Processed Data!AW14 | `='[1]Processed Data'!AW14` |
| 29 | HNX | =[1]Processed Data!AW15 | `='[1]Processed Data'!AW15` |
| 30 | UPCOM | =[1]Processed Data!AW16 | `='[1]Processed Data'!AW16` |
| 32 | ADTV | (tiêu đề nhóm) | `` |
| 33 | HOSE | =[1]Processed Data!AW20 | `='[1]Processed Data'!AW20` |
| 34 | HNX | =[1]Processed Data!AW21 | `='[1]Processed Data'!AW21` |
| 35 | UPCOM | =[1]Processed Data!AW22 | `='[1]Processed Data'!AW22` |
| 39 | Tài khoản mở mới | =kỳ cột | `=AP$8` |
| 40 | Cá nhân | =SốTK[Cá nhân mở thêm  (TK) \| Quarters (Date)=kỳ cột, Years (Date)=kỳ cột] | `=GETPIVOTDATA("Sum of Cá nhân mở thêm  (TK)",'Số TK mở mới'!$AK$35,"Quarters (Date)",AP$10,"Years (Date)",AP$9)` |
| 41 | Tổ chức | =SUMIFS(SốTK[cột Tổ chức mở thêm (TK)] (dòng 8..133),SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39) | `=SUMIFS('Số TK mở mới'!$L$8:$L$133,'Số TK mở mới'!$P$8:$P$133,AP$39)` |
| 43 | Cá nhân NN | =IF(COUNTIF(SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39)=0,"",SUMIFS(SốTK[cột Cá nhân NN] (dòng 8..133),SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39,SốTK[cột Date] (dòng 8..133),MAXIFS(SốTK[cột Date] (dòng 8..133),SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39))-SUMIFS(SốTK[cột Cá nhân NN] (dòng 8..133),SốTK[cột Date] (dòng 8..133),MAXIFS(SốTK[cột Date] (dòng 8..133),SốTK[cột Date] (dòng 8..133),"<"&MINIFS(SốTK[cột Date] (dòng 8..133),SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39)))) | `=IF(COUNTIF('Số TK mở mới'!$P$8:$P$133,AP$39)=0,"",SUMIFS('Số TK mở mới'!$H$8:$H$133,'Số TK mở mới'!$P$8:$P$133,AP$39,'Số TK mở mới'!$E$8:$E$133,_xlfn.MAXIFS('Số TK mở mới'!$E$8:$E$133,'Số TK mở mới'!$P$8:$P$133,AP$39))-SUMIFS('Số TK mở mới'!$H$8:$H$133,'Số TK mở mới'!$E$8:$E$133,_xlfn.MAXIFS('Số TK` |
| 44 | Tổ chức NN | =IF(COUNTIF(SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39)=0,"",SUMIFS(SốTK[cột Tổ chức NN] (dòng 8..133),SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39,SốTK[cột Date] (dòng 8..133),MAXIFS(SốTK[cột Date] (dòng 8..133),SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39))-SUMIFS(SốTK[cột Tổ chức NN] (dòng 8..133),SốTK[cột Date] (dòng 8..133),MAXIFS(SốTK[cột Date] (dòng 8..133),SốTK[cột Date] (dòng 8..133),"<"&MINIFS(SốTK[cột Date] (dòng 8..133),SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39)))) | `=IF(COUNTIF('Số TK mở mới'!$P$8:$P$133,AP$39)=0,"",SUMIFS('Số TK mở mới'!$I$8:$I$133,'Số TK mở mới'!$P$8:$P$133,AP$39,'Số TK mở mới'!$E$8:$E$133,_xlfn.MAXIFS('Số TK mở mới'!$E$8:$E$133,'Số TK mở mới'!$P$8:$P$133,AP$39))-SUMIFS('Số TK mở mới'!$I$8:$I$133,'Số TK mở mới'!$E$8:$E$133,_xlfn.MAXIFS('Số TK` |
| 46 | Tài khoản lũy kế | (tiêu đề nhóm) | `` |
| 47 | Cá nhân | =IF(COUNTIF(SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39)=0,"",SUMIFS(SốTK[cột Cá nhân] (dòng 8..133),SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39,SốTK[cột Date] (dòng 8..133),MAXIFS(SốTK[cột Date] (dòng 8..133),SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39))) | `=IF(COUNTIF('Số TK mở mới'!$P$8:$P$133,AP$39)=0,"",SUMIFS('Số TK mở mới'!$F$8:$F$133,'Số TK mở mới'!$P$8:$P$133,AP$39,'Số TK mở mới'!$E$8:$E$133,_xlfn.MAXIFS('Số TK mở mới'!$E$8:$E$133,'Số TK mở mới'!$P$8:$P$133,AP$39)))` |
| 48 | Tổ chức | =IF(COUNTIF(SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39)=0,"",SUMIFS(SốTK[cột Tổ chức] (dòng 8..133),SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39,SốTK[cột Date] (dòng 8..133),MAXIFS(SốTK[cột Date] (dòng 8..133),SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39))) | `=IF(COUNTIF('Số TK mở mới'!$P$8:$P$133,AP$39)=0,"",SUMIFS('Số TK mở mới'!$G$8:$G$133,'Số TK mở mới'!$P$8:$P$133,AP$39,'Số TK mở mới'!$E$8:$E$133,_xlfn.MAXIFS('Số TK mở mới'!$E$8:$E$133,'Số TK mở mới'!$P$8:$P$133,AP$39)))` |
| 50 | Cá nhân NN | =IF(COUNTIF(SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39)=0,"",SUMIFS(SốTK[cột Cá nhân NN] (dòng 8..133),SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39,SốTK[cột Date] (dòng 8..133),MAXIFS(SốTK[cột Date] (dòng 8..133),SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39))) | `=IF(COUNTIF('Số TK mở mới'!$P$8:$P$133,AP$39)=0,"",SUMIFS('Số TK mở mới'!$H$8:$H$133,'Số TK mở mới'!$P$8:$P$133,AP$39,'Số TK mở mới'!$E$8:$E$133,_xlfn.MAXIFS('Số TK mở mới'!$E$8:$E$133,'Số TK mở mới'!$P$8:$P$133,AP$39)))` |
| 51 | Tổ chức NN | =IF(COUNTIF(SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39)=0,"",SUMIFS(SốTK[cột Tổ chức NN] (dòng 8..133),SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39,SốTK[cột Date] (dòng 8..133),MAXIFS(SốTK[cột Date] (dòng 8..133),SốTK[cột Time] (dòng 8..133),[Tài khoản mở mới]#39))) | `=IF(COUNTIF('Số TK mở mới'!$P$8:$P$133,AP$39)=0,"",SUMIFS('Số TK mở mới'!$I$8:$I$133,'Số TK mở mới'!$P$8:$P$133,AP$39,'Số TK mở mới'!$E$8:$E$133,_xlfn.MAXIFS('Số TK mở mới'!$E$8:$E$133,'Số TK mở mới'!$P$8:$P$133,AP$39)))` |
| 54 | Nguồn vốn | =kỳ cột | `=AP$8` |
| 55 | Room margin | =IF([Room margin]#55 (ô @G55 trống)="",IFERROR(INDEX(FS Industry![Loans (margin)]#43 46 kỳ gần nhất,MATCH(kỳ cột,kỳ cột 46 kỳ gần nhất,0))/(2*INDEX(FS Industry![Owner's equity]#53 46 kỳ gần nhất,MATCH(kỳ cột,kỳ cột 46 kỳ gần nhất,0))),""),IFERROR(DATA[mã=[Room margin]#55 (ô @G55 trống); TRIM("Các khoản cho vay") \| dòng"8"\| kỳ cột]/(2*DATA[mã=[Room margin]#55 (ô @G55 trống); TRIM("VỐN CHỦ SỞ HỮU") \| dòng"142"\| kỳ cột]),"")) | `=IF($G55="",IFERROR(INDEX('FS Industry'!$U$43:$BN$43,MATCH(AP$8,'FS Industry'!$U$4:$BN$4,0))/(2*INDEX('FS Industry'!$U$53:$BN$53,MATCH(AP$8,'FS Industry'!$U$4:$BN$4,0))),""),IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G55,"row_order",BS!$B$15,"metric",TRIM(BS!$A$15),"year",RIGHT(AP$8,4)+0,"quar` |
| 57 | VSCH | =IF([Room margin]#55 (ô @G55 trống)="",IFERROR(INDEX(FS Industry![Owner's equity]#53 46 kỳ gần nhất,MATCH(kỳ cột,kỳ cột 46 kỳ gần nhất,0)),""),IFERROR(DATA[mã=[Room margin]#55 (ô @G55 trống); TRIM("VỐN CHỦ SỞ HỮU") \| dòng"142"\| kỳ cột],"")) | `=IF($G55="",IFERROR(INDEX('FS Industry'!$U$53:$BN$53,MATCH(AP$8,'FS Industry'!$U$4:$BN$4,0)),""),IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G55,"row_order",BS!$B$149,"metric",TRIM(BS!$A$149),"year",RIGHT(AP$8,4)+0,"quarter",MID(AP$8,2,1)+0),""))` |
| 58 | Vốn góp | =IF([Room margin]#55 (ô @G55 trống)="",IFERROR(INDEX(FS Industry![Paid-in capital]#54 46 kỳ gần nhất,MATCH(kỳ cột,kỳ cột 46 kỳ gần nhất,0)),""),IFERROR(DATA[mã=[Room margin]#55 (ô @G55 trống); TRIM("Vốn góp của chủ sở hữu") \| dòng"145"\| kỳ cột],"")) | `=IF($G55="",IFERROR(INDEX('FS Industry'!$U$54:$BN$54,MATCH(AP$8,'FS Industry'!$U$4:$BN$4,0)),""),IFERROR(GETPIVOTDATA("value",DATA!$A$3,"ticker",$G55,"row_order",BS!$B$152,"metric",TRIM(BS!$A$152),"year",RIGHT(AP$8,4)+0,"quarter",MID(AP$8,2,1)+0),""))` |
| 59 | LN giữ lại và quỹ | =IFERROR([VSCH]#57-[Vốn góp]#58,"") | `=IFERROR(AP57-AP58,"")` |
| 61 | Tăng vốn | =IFERROR([Vốn góp]#58-[Vốn góp]#58(-1 kỳ),"") | `=IFERROR(AP58-AO58,"")` |
| 62 | Trích quỹ và LN | =IFERROR([LN giữ lại và quỹ]#59-[LN giữ lại và quỹ]#59(-1 kỳ),"") | `=IFERROR(AP59-AO59,"")` |