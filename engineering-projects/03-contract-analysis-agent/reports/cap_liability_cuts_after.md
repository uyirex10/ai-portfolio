# Cap On Liability -- cut-across cases (dev set, PyMuPDF extraction)

Dev-set PDF-only contracts: 157. Cap On Liability spans cut across 2+ splitter clauses: **10**.

The "trigger" label for each cut is **inferred** from the shape of the clause id/heading that starts partway through the labeled span (e.g. a dotted id like `4.2` implies a dotted sub-number boundary fired there) -- it is not read out of segment.py's internal regex state (this report does not modify or introspect segment.py beyond its public API), so treat it as a best-effort classification for grouping, not a guaranteed trace of which rule fired.

## plain numbered, no heading ("N.") (16 cases)

### ZogenixInc_20190509_10-Q_EX-10.2_11663313_EX-10.2_Distributor Agreement

**Labeled span (Cap On Liability):**
```
NEITHER PARTY SHALL BE ENTITLED TO RECOVER FROM THE OTHER PARTY ANY SPECIAL, INCIDENTAL, CONSEQUENTIAL OR PUNITIVE DAMAGES IN CONNECTION WITH THIS AGREEMENT; provided however, that this Section 10.5 shall not be construed to limit (a) either Party's right to special, incidental or consequential damages for the other Party's breach of Article 8 or (b) either Party's indemnification rights or obligations under Article 11.
```
**Cut boundary:** new clause `id='11'` heading=None begins at offset 130112 (span runs 129700-130123)

**200 chars before the cut:**
```
construed to limit (a) either Party’s right to special, incidental
or consequential damages for the other Party’s breach of Article 8 or (b) either Party’s indemnification rights or obligations under

```
**200 chars after the cut (start of new clause):**
```
Article 11.
ARTICLE 11.
INDEMNIFICATION
11.1 Indemnification of Zogenix. Distributor shall indemnify, defend and hold harmless Zogenix and its Affiliates and
their respective directors, officers, empl
```

### XENCORINC_10_25_2013-EX-10.24-COLLABORATION AGREEMENT (3)

**Labeled span (Cap On Liability):**
```
For avoidance of doubt, all BII liability or indemnification obligation that might result from representations and the warranties under this Section 6 are always subject to the limitations set forth in Section 7.4 of this Agreement.
```
**Cut boundary:** new clause `id='6'` heading=None begins at offset 70378 (span runs 70237-70469)

**200 chars before the cut:**
```
gy and/or the Process, or any part or component thereof.
 
For avoidance of doubt, all BII liability or indemnification obligation that might result from representations and the warranties under this

```
**200 chars after the cut (start of new clause):**
```
Section 6 are always subject to the limitations set forth in Section 7.4 of this Agreement.
 
6.4 Process for Defense of Infringement of Third Party Intellectual Property
 
Subject to each Party’s ind
```

### BLUEROCKRESIDENTIALGROWTHREIT,INC_06_01_2016-EX-1.1-AGENCY AGREEMENT

**Labeled span (Cap On Liability):**
```
Notwithstanding the provisions of this Section 8(d), the Agent shall not be required to contribute any amount in excess of the amount by which the total price at which the  Series A Preferred Stock sold pursuant to this Agreement exceeds the amount of any damages which the Agent has otherwise been required to pay by reason of such untrue or alleged untrue statement or omission or alleged omission.
```
**Cut boundary:** new clause `id='8'` heading=None begins at offset 122983 (span runs 122944-123344)

**200 chars before the cut:**
```
enses reasonably incurred by such indemnified party in connection with
investigating or defending any action or claim which is the subject of this Section 8(d). Notwithstanding the provisions of this

```
**200 chars after the cut (start of new clause):**
```
Section 8(d), the Agent shall not be required to contribute any amount in excess of the amount by which the total price at which
the  Series A Preferred Stock sold pursuant to this Agreement exceeds t
```

### SUNTRONCORP_05_17_2006-EX-10.22-MAINTENANCE AGREEMENT

**Labeled span (Cap On Liability):**
```
The Investor acknowledges and agrees that if a Maintenance Event of Default (as defined in Section 10 below) has occurred and is continuing hereunder, the Agent, for itself and on behalf of the Lenders, shall have the non-exclusive right to





obtain specific performance of the obligation of the Investor to make the Required Capital Contributions.
```
**Cut boundary:** new clause `id='10'` heading=None begins at offset 5282 (span runs 5191-5538)

**200 chars before the cut:**
```
, ninety (90) days following such fiscal
year end.
          4. Specific Performance and Liquidated Damages. The Investor
acknowledges and agrees that if a Maintenance Event of Default (as defined in

```
**200 chars after the cut (start of new clause):**
```
Section 10 below) has occurred and is continuing hereunder, the Agent, for
itself and on behalf of the Lenders, shall have the non-exclusive right to

obtain specific performance of the obligation of 
```

### TELKOMSALTD_01_30_2003-EX-10-LICENCE AND MAINTENANCE AGREEMENT

**Labeled span (Cap On Liability):**
```
TELKOM'S sole and exclusive remedies for any breach of SAP AFRICA'S   warranties contained in clause 10 shall, at SAP AFRICA'S option, be either:   11. 1. 1       replacement of the SOFTWARE and/or performance of services in respect   thereof; or   11. 1. 2       return or credit of an appropriate portion of any payment made, or to be   made, by TELKOM with respect to the defective portion, or the whole of the   SOFTWARE or Maintenance Services, but excluding the License Fee or any   portion thereof.   SAP AFRICA must exercise its option within 20 days of first becoming aware of the   defect.
```
**Cut boundary:** new clause `id='11'` heading=None begins at offset 44486 (span runs 44342-44923)

**200 chars before the cut:**
```
S
vest in TELKOM.
11    LIMITATION OF LIABILITY
11. 1   TELKOM'S sole and exclusive remedies for any breach of SAP AFRICA'S
warranties contained in clause 10 shall, at SAP AFRICA'S option, be either:

```
**200 chars after the cut (start of new clause):**
```
11. 1. 1       replacement of the SOFTWARE and/or performance of services in respect
thereof; or
11. 1. 2       return or credit of an appropriate portion of any payment made, or to be
made, by TELKOM
```

### TELKOMSALTD_01_30_2003-EX-10-LICENCE AND MAINTENANCE AGREEMENT

**Labeled span (Cap On Liability):**
```
TELKOM'S sole and exclusive remedies for any breach of SAP AFRICA'S   warranties contained in clause 10 shall, at SAP AFRICA'S option, be either:   11. 1. 1       replacement of the SOFTWARE and/or performance of services in respect   thereof; or   11. 1. 2       return or credit of an appropriate portion of any payment made, or to be   made, by TELKOM with respect to the defective portion, or the whole of the   SOFTWARE or Maintenance Services, but excluding the License Fee or any   portion thereof.   SAP AFRICA must exercise its option within 20 days of first becoming aware of the   defect.
```
**Cut boundary:** new clause `id='1'` heading=None begins at offset 44490 (span runs 44342-44923)

**200 chars before the cut:**
```
st in TELKOM.
11    LIMITATION OF LIABILITY
11. 1   TELKOM'S sole and exclusive remedies for any breach of SAP AFRICA'S
warranties contained in clause 10 shall, at SAP AFRICA'S option, be either:
11. 
```
**200 chars after the cut (start of new clause):**
```
1. 1       replacement of the SOFTWARE and/or performance of services in respect
thereof; or
11. 1. 2       return or credit of an appropriate portion of any payment made, or to be
made, by TELKOM wit
```

### TELKOMSALTD_01_30_2003-EX-10-LICENCE AND MAINTENANCE AGREEMENT

**Labeled span (Cap On Liability):**
```
TELKOM'S sole and exclusive remedies for any breach of SAP AFRICA'S   warranties contained in clause 10 shall, at SAP AFRICA'S option, be either:   11. 1. 1       replacement of the SOFTWARE and/or performance of services in respect   thereof; or   11. 1. 2       return or credit of an appropriate portion of any payment made, or to be   made, by TELKOM with respect to the defective portion, or the whole of the   SOFTWARE or Maintenance Services, but excluding the License Fee or any   portion thereof.   SAP AFRICA must exercise its option within 20 days of first becoming aware of the   defect.
```
**Cut boundary:** new clause `id='11'` heading=None begins at offset 44583 (span runs 44342-44923)

**200 chars before the cut:**
```
any breach of SAP AFRICA'S
warranties contained in clause 10 shall, at SAP AFRICA'S option, be either:
11. 1. 1       replacement of the SOFTWARE and/or performance of services in respect
thereof; or

```
**200 chars after the cut (start of new clause):**
```
11. 1. 2       return or credit of an appropriate portion of any payment made, or to be
made, by TELKOM with respect to the defective portion, or the whole of the
SOFTWARE or Maintenance Services, but
```

### TELKOMSALTD_01_30_2003-EX-10-LICENCE AND MAINTENANCE AGREEMENT

**Labeled span (Cap On Liability):**
```
TELKOM'S sole and exclusive remedies for any breach of SAP AFRICA'S   warranties contained in clause 10 shall, at SAP AFRICA'S option, be either:   11. 1. 1       replacement of the SOFTWARE and/or performance of services in respect   thereof; or   11. 1. 2       return or credit of an appropriate portion of any payment made, or to be   made, by TELKOM with respect to the defective portion, or the whole of the   SOFTWARE or Maintenance Services, but excluding the License Fee or any   portion thereof.   SAP AFRICA must exercise its option within 20 days of first becoming aware of the   defect.
```
**Cut boundary:** new clause `id='1'` heading=None begins at offset 44587 (span runs 44342-44923)

**200 chars before the cut:**
```
breach of SAP AFRICA'S
warranties contained in clause 10 shall, at SAP AFRICA'S option, be either:
11. 1. 1       replacement of the SOFTWARE and/or performance of services in respect
thereof; or
11. 
```
**200 chars after the cut (start of new clause):**
```
1. 2       return or credit of an appropriate portion of any payment made, or to be
made, by TELKOM with respect to the defective portion, or the whole of the
SOFTWARE or Maintenance Services, but exc
```

### TELKOMSALTD_01_30_2003-EX-10-LICENCE AND MAINTENANCE AGREEMENT

**Labeled span (Cap On Liability):**
```
For the avoidance of doubt, it is recorded that SAP AFRICA will not be liable under   this AGREEMENT for:   11. 3. 1       the MODIFICATION or improvement of the SOFTWARE by TELKOM to fit   the particular requirements of TELKOM; or   11. 3. 2       the correction of any data errors resulting from MODIFICATIONS or   EXTENSIONS by TELKOM or its agents; or   11. 3. 3       the correction of any data errors as a result of misuse of the SOFTWARE by   TELKOM or its agents; or   11. 3. 4       preparation or conversion of data by TELKOM into the form required for use   with the SOFTWARE.
```
**Cut boundary:** new clause `id='11'` heading=None begins at offset 45223 (span runs 45119-45688)

**200 chars before the cut:**
```
 below.

- 30 -                                             TELKOM CONTRACT No. 076C/01
11. 3   For the avoidance of doubt, it is recorded that SAP AFRICA will not be liable under
this AGREEMENT for:

```
**200 chars after the cut (start of new clause):**
```
11. 3. 1       the MODIFICATION or improvement of the SOFTWARE by TELKOM to fit
the particular requirements of TELKOM; or
11. 3. 2       the correction of any data errors resulting from MODIFICATIONS 
```

### TELKOMSALTD_01_30_2003-EX-10-LICENCE AND MAINTENANCE AGREEMENT

**Labeled span (Cap On Liability):**
```
For the avoidance of doubt, it is recorded that SAP AFRICA will not be liable under   this AGREEMENT for:   11. 3. 1       the MODIFICATION or improvement of the SOFTWARE by TELKOM to fit   the particular requirements of TELKOM; or   11. 3. 2       the correction of any data errors resulting from MODIFICATIONS or   EXTENSIONS by TELKOM or its agents; or   11. 3. 3       the correction of any data errors as a result of misuse of the SOFTWARE by   TELKOM or its agents; or   11. 3. 4       preparation or conversion of data by TELKOM into the form required for use   with the SOFTWARE.
```
**Cut boundary:** new clause `id='3'` heading=None begins at offset 45227 (span runs 45119-45688)

**200 chars before the cut:**
```
ow.

- 30 -                                             TELKOM CONTRACT No. 076C/01
11. 3   For the avoidance of doubt, it is recorded that SAP AFRICA will not be liable under
this AGREEMENT for:
11. 
```
**200 chars after the cut (start of new clause):**
```
3. 1       the MODIFICATION or improvement of the SOFTWARE by TELKOM to fit
the particular requirements of TELKOM; or
11. 3. 2       the correction of any data errors resulting from MODIFICATIONS or
E
```

### TELKOMSALTD_01_30_2003-EX-10-LICENCE AND MAINTENANCE AGREEMENT

**Labeled span (Cap On Liability):**
```
For the avoidance of doubt, it is recorded that SAP AFRICA will not be liable under   this AGREEMENT for:   11. 3. 1       the MODIFICATION or improvement of the SOFTWARE by TELKOM to fit   the particular requirements of TELKOM; or   11. 3. 2       the correction of any data errors resulting from MODIFICATIONS or   EXTENSIONS by TELKOM or its agents; or   11. 3. 3       the correction of any data errors as a result of misuse of the SOFTWARE by   TELKOM or its agents; or   11. 3. 4       preparation or conversion of data by TELKOM into the form required for use   with the SOFTWARE.
```
**Cut boundary:** new clause `id='11'` heading=None begins at offset 45345 (span runs 45119-45688)

**200 chars before the cut:**
```
, it is recorded that SAP AFRICA will not be liable under
this AGREEMENT for:
11. 3. 1       the MODIFICATION or improvement of the SOFTWARE by TELKOM to fit
the particular requirements of TELKOM; or

```
**200 chars after the cut (start of new clause):**
```
11. 3. 2       the correction of any data errors resulting from MODIFICATIONS or
EXTENSIONS by TELKOM or its agents; or
11. 3. 3       the correction of any data errors as a result of misuse of the SO
```

### TELKOMSALTD_01_30_2003-EX-10-LICENCE AND MAINTENANCE AGREEMENT

**Labeled span (Cap On Liability):**
```
For the avoidance of doubt, it is recorded that SAP AFRICA will not be liable under   this AGREEMENT for:   11. 3. 1       the MODIFICATION or improvement of the SOFTWARE by TELKOM to fit   the particular requirements of TELKOM; or   11. 3. 2       the correction of any data errors resulting from MODIFICATIONS or   EXTENSIONS by TELKOM or its agents; or   11. 3. 3       the correction of any data errors as a result of misuse of the SOFTWARE by   TELKOM or its agents; or   11. 3. 4       preparation or conversion of data by TELKOM into the form required for use   with the SOFTWARE.
```
**Cut boundary:** new clause `id='3'` heading=None begins at offset 45349 (span runs 45119-45688)

**200 chars before the cut:**
```
 is recorded that SAP AFRICA will not be liable under
this AGREEMENT for:
11. 3. 1       the MODIFICATION or improvement of the SOFTWARE by TELKOM to fit
the particular requirements of TELKOM; or
11. 
```
**200 chars after the cut (start of new clause):**
```
3. 2       the correction of any data errors resulting from MODIFICATIONS or
EXTENSIONS by TELKOM or its agents; or
11. 3. 3       the correction of any data errors as a result of misuse of the SOFTWA
```

### TELKOMSALTD_01_30_2003-EX-10-LICENCE AND MAINTENANCE AGREEMENT

**Labeled span (Cap On Liability):**
```
For the avoidance of doubt, it is recorded that SAP AFRICA will not be liable under   this AGREEMENT for:   11. 3. 1       the MODIFICATION or improvement of the SOFTWARE by TELKOM to fit   the particular requirements of TELKOM; or   11. 3. 2       the correction of any data errors resulting from MODIFICATIONS or   EXTENSIONS by TELKOM or its agents; or   11. 3. 3       the correction of any data errors as a result of misuse of the SOFTWARE by   TELKOM or its agents; or   11. 3. 4       preparation or conversion of data by TELKOM into the form required for use   with the SOFTWARE.
```
**Cut boundary:** new clause `id='11'` heading=None begins at offset 45465 (span runs 45119-45688)

**200 chars before the cut:**
```
ment of the SOFTWARE by TELKOM to fit
the particular requirements of TELKOM; or
11. 3. 2       the correction of any data errors resulting from MODIFICATIONS or
EXTENSIONS by TELKOM or its agents; or

```
**200 chars after the cut (start of new clause):**
```
11. 3. 3       the correction of any data errors as a result of misuse of the SOFTWARE by
TELKOM or its agents; or
11. 3. 4       preparation or conversion of data by TELKOM into the form required for
```

### TELKOMSALTD_01_30_2003-EX-10-LICENCE AND MAINTENANCE AGREEMENT

**Labeled span (Cap On Liability):**
```
For the avoidance of doubt, it is recorded that SAP AFRICA will not be liable under   this AGREEMENT for:   11. 3. 1       the MODIFICATION or improvement of the SOFTWARE by TELKOM to fit   the particular requirements of TELKOM; or   11. 3. 2       the correction of any data errors resulting from MODIFICATIONS or   EXTENSIONS by TELKOM or its agents; or   11. 3. 3       the correction of any data errors as a result of misuse of the SOFTWARE by   TELKOM or its agents; or   11. 3. 4       preparation or conversion of data by TELKOM into the form required for use   with the SOFTWARE.
```
**Cut boundary:** new clause `id='3'` heading=None begins at offset 45469 (span runs 45119-45688)

**200 chars before the cut:**
```
 of the SOFTWARE by TELKOM to fit
the particular requirements of TELKOM; or
11. 3. 2       the correction of any data errors resulting from MODIFICATIONS or
EXTENSIONS by TELKOM or its agents; or
11. 
```
**200 chars after the cut (start of new clause):**
```
3. 3       the correction of any data errors as a result of misuse of the SOFTWARE by
TELKOM or its agents; or
11. 3. 4       preparation or conversion of data by TELKOM into the form required for use
```

### TELKOMSALTD_01_30_2003-EX-10-LICENCE AND MAINTENANCE AGREEMENT

**Labeled span (Cap On Liability):**
```
For the avoidance of doubt, it is recorded that SAP AFRICA will not be liable under   this AGREEMENT for:   11. 3. 1       the MODIFICATION or improvement of the SOFTWARE by TELKOM to fit   the particular requirements of TELKOM; or   11. 3. 2       the correction of any data errors resulting from MODIFICATIONS or   EXTENSIONS by TELKOM or its agents; or   11. 3. 3       the correction of any data errors as a result of misuse of the SOFTWARE by   TELKOM or its agents; or   11. 3. 4       preparation or conversion of data by TELKOM into the form required for use   with the SOFTWARE.
```
**Cut boundary:** new clause `id='11'` heading=None begins at offset 45580 (span runs 45119-45688)

**200 chars before the cut:**
```
y data errors resulting from MODIFICATIONS or
EXTENSIONS by TELKOM or its agents; or
11. 3. 3       the correction of any data errors as a result of misuse of the SOFTWARE by
TELKOM or its agents; or

```
**200 chars after the cut (start of new clause):**
```
11. 3. 4       preparation or conversion of data by TELKOM into the form required for use
with the SOFTWARE.
11. 4   Subject to, and without prejudice to the provisions of this clause 11. 1 and clause
```

### TELKOMSALTD_01_30_2003-EX-10-LICENCE AND MAINTENANCE AGREEMENT

**Labeled span (Cap On Liability):**
```
For the avoidance of doubt, it is recorded that SAP AFRICA will not be liable under   this AGREEMENT for:   11. 3. 1       the MODIFICATION or improvement of the SOFTWARE by TELKOM to fit   the particular requirements of TELKOM; or   11. 3. 2       the correction of any data errors resulting from MODIFICATIONS or   EXTENSIONS by TELKOM or its agents; or   11. 3. 3       the correction of any data errors as a result of misuse of the SOFTWARE by   TELKOM or its agents; or   11. 3. 4       preparation or conversion of data by TELKOM into the form required for use   with the SOFTWARE.
```
**Cut boundary:** new clause `id='3'` heading=None begins at offset 45584 (span runs 45119-45688)

**200 chars before the cut:**
```
ta errors resulting from MODIFICATIONS or
EXTENSIONS by TELKOM or its agents; or
11. 3. 3       the correction of any data errors as a result of misuse of the SOFTWARE by
TELKOM or its agents; or
11. 
```
**200 chars after the cut (start of new clause):**
```
3. 4       preparation or conversion of data by TELKOM into the form required for use
with the SOFTWARE.
11. 4   Subject to, and without prejudice to the provisions of this clause 11. 1 and clause
10,
```

## dotted sub-number (N.M...) (3 cases)

### PaperexchangeComInc_20000322_S-1A_EX-10.4_5202103_EX-10.4_Co-Branding Agreement

**Labeled span (Cap On Liability):**
```
EXCEPT IN CONNECTION WITH A BREACH BY EITHER PARTY OF ARTICLE 10, THE INDEMNIFICATION OBLIGATIONS OF PAPEREXCHANGE UNDER SECTIONS 12.4(c)  [Indemnification by PaperExchange] AND THE INDEMNIFICATION OBLIGATIONS OF VERTICALNET UNDER SECTION 12.5(c)  [Indemnification by VerticalNet], NEITHER PARTY WILL BE LIABLE FOR ANY SPECIAL, INDIRECT, CONSEQUENTIAL, EXEMPLARY OR INCIDENTAL DAMAGES ARISING OUT OF OR RELATED TO THIS AGREEMENT, HOWEVER CAUSED AND UNDER ANY THEORY OF LIABILITY (INCLUDING NEGLIGENCE), EVEN IF SUCH PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.
```
**Cut boundary:** new clause `id='12.5'` heading=None begins at offset 58430 (span runs 58199-58773)

**200 chars before the cut:**
```
ACH BY
EITHER PARTY OF ARTICLE 10, THE INDEMNIFICATION OBLIGATIONS OF PAPEREXCHANGE
UNDER SECTIONS 12.4(c)  [Indemnification by PaperExchange] AND THE INDEMNIFICATION OBLIGATIONS OF VERTICALNET UNDER

```
**200 chars after the cut (start of new clause):**
```
SECTION 12.5(c)  [Indemnification by VerticalNet], NEITHER PARTY WILL BE LIABLE FOR ANY SPECIAL, INDIRECT,
CONSEQUENTIAL, EXEMPLARY OR INCIDENTAL DAMAGES ARISING OUT OF OR RELATED TO THIS
AGREEMENT, H
```

### RandWorldwideInc_20010402_8-KA_EX-10.2_2102464_EX-10.2_Co-Branding Agreement

**Labeled span (Cap On Liability):**
```
EXCEPT FOR LIABILITY ARISING FROM SECTION 9.3  [Intellectual Property Infringement], IN NO EVENT SHALL EITHER PARTY BE LIABLE UNDER THIS AGREEMENT FOR AN AMOUNT GREATER THAN THE AMOUNT THAT SUCH PARTY HAS EARNED PURSUANT TO THE REVENUE SHARING PROVISIONS OF SECTION 5.4  [Share of Net Revenue] IN THE TWELVE MONTH PERIOD PRECEDING THE CLAIM.
```
**Cut boundary:** new clause `id='5.4'` heading=None begins at offset 35898 (span runs 35640-35981)

**200 chars before the cut:**
```
al Property Infringement], IN NO EVENT
SHALL EITHER PARTY BE LIABLE UNDER THIS AGREEMENT FOR AN AMOUNT GREATER THAN THE
AMOUNT THAT SUCH PARTY HAS EARNED PURSUANT TO THE REVENUE SHARING PROVISIONS OF

```
**200 chars after the cut (start of new clause):**
```
SECTION 5.4  [Share of Net Revenue] IN THE TWELVE MONTH PERIOD PRECEDING THE CLAIM.
                                   SECTION 10
                              TERM AND TERMINATION
                  1
```

### ADIANUTRITION,INC_04_01_2005-EX-10.D2-RESELLER AGREEMENT

**Labeled span (Cap On Liability):**
```
In the event of termination in accordance with Section 5.1, PivX shall not be liable to Detto because of such termination for compensation, reimbursement or damages on account of the loss of prospective profits or anticipated sales or on account of expenditures, inventory, investments, leases or commitments in connection with the business or goodwill of Detto.
```
**Cut boundary:** new clause `id='5.1'` heading=None begins at offset 20467 (span runs 20420-20782)

**200 chars before the cut:**
```
Section 2.2, Sections 2.3 through and including 2.9,
Section 3.6, Section 4, this Section 5 and Section 6. 5.4 LIMITATION OF
LIABILITY UPON TERMINATION. In the event of termination in accordance with

```
**200 chars after the cut (start of new clause):**
```
Section 5.1, PivX shall not be liable to Detto because of such termination for
compensation, reimbursement or damages on account of the loss of prospective
profits or anticipated sales or on account o
```

## lettered sub-item ((a), (b), ...) (2 cases)

### ZogenixInc_20190509_10-Q_EX-10.2_11663313_EX-10.2_Distributor Agreement

**Labeled span (Cap On Liability):**
```
NEITHER PARTY SHALL BE ENTITLED TO RECOVER FROM THE OTHER PARTY ANY SPECIAL, INCIDENTAL, CONSEQUENTIAL OR PUNITIVE DAMAGES IN CONNECTION WITH THIS AGREEMENT; provided however, that this Section 10.5 shall not be construed to limit (a) either Party's right to special, incidental or consequential damages for the other Party's breach of Article 8 or (b) either Party's indemnification rights or obligations under Article 11.
```
**Cut boundary:** new clause `id='a'` heading=None begins at offset 129931 (span runs 129700-130123)

**200 chars before the cut:**
```
 TO RECOVER FROM THE OTHER
PARTY ANY SPECIAL, INCIDENTAL, CONSEQUENTIAL OR PUNITIVE DAMAGES IN CONNECTION WITH THIS
AGREEMENT; provided however, that this Section 10.5 shall not be construed to limit 
```
**200 chars after the cut (start of new clause):**
```
(a) either Party’s right to special, incidental
or consequential damages for the other Party’s breach of Article 8 or (b) either Party’s indemnification rights or obligations under
Article 11.
ARTICLE
```

### ZogenixInc_20190509_10-Q_EX-10.2_11663313_EX-10.2_Distributor Agreement

**Labeled span (Cap On Liability):**
```
NEITHER PARTY SHALL BE ENTITLED TO RECOVER FROM THE OTHER PARTY ANY SPECIAL, INCIDENTAL, CONSEQUENTIAL OR PUNITIVE DAMAGES IN CONNECTION WITH THIS AGREEMENT; provided however, that this Section 10.5 shall not be construed to limit (a) either Party's right to special, incidental or consequential damages for the other Party's breach of Article 8 or (b) either Party's indemnification rights or obligations under Article 11.
```
**Cut boundary:** new clause `id='b'` heading=None begins at offset 130049 (span runs 129700-130123)

**200 chars before the cut:**
```
REEMENT; provided however, that this Section 10.5 shall not be construed to limit (a) either Party’s right to special, incidental
or consequential damages for the other Party’s breach of Article 8 or 
```
**200 chars after the cut (start of new clause):**
```
(b) either Party’s indemnification rights or obligations under
Article 11.
ARTICLE 11.
INDEMNIFICATION
11.1 Indemnification of Zogenix. Distributor shall indemnify, defend and hold harmless Zogenix an
```

## plain numbered with heading ("N. Heading") (1 cases)

### KUBIENT,INC_07_02_2020-EX-10.14-MASTER SERVICES AGREEMENT_Part1

**Labeled span (Cap On Liability):**
```
EXCEPT WITH RESPECT TO THE PARTIES' LIABILITY FOR INDEMNIFICATION, OR LIABILITY FOR BREACH OF CONFIDENTIALITY, NEITHER PARTY SHALL BE LIABLE FOR ANY CONSEQUENTIAL, INCIDENTAL, INDIRECT, PUNITIVE, SPECIAL OR OTHER SIMILAR DAMAGES, WHETHER OR NOT CAUSED BY THE OTHER PARTY'S EMPLOYEES OR REPRESENTATIVES„ WHETHER UNDER TORT (INCLUDING NEGLIGENCE), CONTRACT OR OTHER THEORIES OF RECOVERY, EVEN IF THE OTHER PARTY WAS OR SHOULD HAVE BEEN AWARE OR WAS ADVISED OF THE POSSIBILITY OF SUCH DAMAGES. 8. Arbitration.
```
**Cut boundary:** new clause `id='8'` heading='Arbitration' begins at offset 8936 (span runs 8445-8951)

**200 chars before the cut:**
```
SENTATIVES„ WHETHER
UNDER TORT (INCLUDING NEGLIGENCE), CONTRACT OR OTHER THEORIES OF RECOVERY, EVEN IF THE OTHER PARTY WAS OR SHOULD
HAVE BEEN AWARE OR WAS ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

```
**200 chars after the cut (start of new clause):**
```
8. Arbitration. Each Party agrees and does waive trial by jury in any action, proceeding or counterclaim brought against the other Party for any
matter whatsoever arising out of or in any way connecte
```
