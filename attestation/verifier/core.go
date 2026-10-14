package main

// Turin-specific prototype verifier. TCB layout and extension OIDs follow
// AMD 56860 (SNP ABI) and 57230 rev 1.00, tables 11/12. The AMD ARK is
// copied from go-sev-guest v0.15.0 and embedded, never trusted from a response.
import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/sha512"
	"crypto/x509"
	_ "embed"
	"encoding/asn1"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"math/big"
	"time"
)

//go:embed amd-turin-ca.pem
var amdCA []byte

type Evidence struct {
	Report []byte `json:"report"`
	Vcek   []byte `json:"vcek"`
	Ask    []byte `json:"ask"`
	Crl    []byte `json:"crl"`
}
type Result struct {
	Verified    bool             `json:"verified"`
	Error       string           `json:"error,omitempty"`
	Measurement string           `json:"measurement,omitempty"`
	HostData    string           `json:"host_data,omitempty"`
	TCB         map[string]uint8 `json:"tcb,omitempty"`
	Scope       string           `json:"scope,omitempty"`
}

func fail(err error) Result { return Result{Error: err.Error()} }
func extension(cert *x509.Certificate, oid string) ([]byte, error) {
	var found []byte
	for _, e := range cert.Extensions {
		if e.Id.String() == oid {
			if found != nil {
				return nil, errors.New("duplicate VCEK extension")
			}
			found = e.Value
		}
	}
	if found == nil {
		return nil, fmt.Errorf("missing VCEK extension %s", oid)
	}
	return found, nil
}
func integer(cert *x509.Certificate, suffix string) (int, error) {
	b, err := extension(cert, "1.3.6.1.4.1.3704.1."+suffix)
	if err != nil {
		return 0, err
	}
	var v int
	rest, err := asn1.Unmarshal(b, &v)
	if err != nil || len(rest) != 0 || v < 0 || v > 255 {
		return 0, errors.New("invalid VCEK integer")
	}
	return v, nil
}
func littleInt(b []byte) *big.Int {
	r := append([]byte(nil), b...)
	for i, j := 0, len(r)-1; i < j; i, j = i+1, j-1 {
		r[i], r[j] = r[j], r[i]
	}
	return new(big.Int).SetBytes(r)
}
func verifyEvidence(input, expected, measurement string) Result {
	var e Evidence
	if err := json.Unmarshal([]byte(input), &e); err != nil {
		return fail(err)
	}
	r := e.Report
	if len(r) != 1184 || binary.LittleEndian.Uint32(r[:4]) != 5 {
		return fail(errors.New("expected exact SNP v5 report"))
	}
	if len(expected) != 64 || !bytes.Equal(r[0x50:0x90], []byte(expected)) {
		return fail(errors.New("challenge/key binding mismatch"))
	}
	if r[0x188] != 0x1a || r[0x189] != 2 || r[0x18a] != 1 {
		return fail(errors.New("unexpected CPU product/stepping"))
	}
	// This deployment deliberately accepts the administrator-recorded CPU guest
	// launch measurement only. It does not identify the application container.
	if measurement == "" || hex.EncodeToString(r[0x90:0xc0]) != measurement {
		return fail(errors.New("CPU guest measurement mismatch"))
	}
	if binary.LittleEndian.Uint32(r[0x30:0x34]) != 0 || binary.LittleEndian.Uint32(r[0x34:0x38]) != 1 || binary.LittleEndian.Uint32(r[0x48:0x4c]) != 0 {
		return fail(errors.New("VMPL/signing algorithm/key mismatch"))
	}
	if binary.LittleEndian.Uint64(r[8:16]) != 0x30000 {
		return fail(errors.New("guest policy mismatch (debug/migration must be off)"))
	}
	// Reject reserved bytes rather than allowing unsupported report fields.
	for _, span := range [][2]int{{0x4c, 0x50}, {0x18b, 0x1a0}, {0x1eb, 0x1ec}, {0x1ef, 0x1f0}, {0x208, 0x2a0}, {0x2d0, 0x2e8}, {0x318, 0x4a0}} {
		if !bytes.Equal(r[span[0]:span[1]], make([]byte, span[1]-span[0])) {
			return fail(errors.New("nonzero reserved report field"))
		}
	}
	_, remaining := pem.Decode(amdCA)
	block, _ := pem.Decode(remaining)
	if block == nil {
		return fail(errors.New("embedded AMD root missing"))
	}
	root, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return fail(err)
	}
	ask, err := x509.ParseCertificate(e.Ask)
	if err != nil {
		return fail(err)
	}
	vcek, err := x509.ParseCertificate(e.Vcek)
	if err != nil {
		return fail(err)
	}
	roots := x509.NewCertPool()
	roots.AddCert(root)
	inter := x509.NewCertPool()
	inter.AddCert(ask)
	now := time.Now()
	chains, err := vcek.Verify(x509.VerifyOptions{Roots: roots, Intermediates: inter, CurrentTime: now, KeyUsages: []x509.ExtKeyUsage{x509.ExtKeyUsageAny}})
	if err != nil {
		return fail(fmt.Errorf("AMD certificate chain: %w", err))
	}
	if len(chains) == 0 || len(chains[0]) != 3 || !bytes.Equal(chains[0][1].Raw, ask.Raw) {
		return fail(errors.New("unexpected AMD chain"))
	}
	crl, err := x509.ParseRevocationList(e.Crl)
	if err != nil {
		return fail(err)
	}
	if err = crl.CheckSignatureFrom(root); err != nil {
		return fail(err)
	}
	if now.Before(crl.ThisUpdate) || !now.Before(crl.NextUpdate) {
		return fail(errors.New("AMD revocation list expired/not yet valid"))
	}
	for _, bad := range crl.RevokedCertificateEntries {
		if bad.SerialNumber.Cmp(ask.SerialNumber) == 0 {
			return fail(errors.New("AMD signing key revoked"))
		}
	}
	version, err := integer(vcek, "1")
	if err != nil || version != 1 {
		return fail(errors.New("unsupported VCEK structure"))
	}
	name, err := extension(vcek, "1.3.6.1.4.1.3704.1.2")
	if err != nil {
		return fail(err)
	}
	var product string
	rest, err := asn1.Unmarshal(name, &product)
	if err != nil || len(rest) != 0 || product != "Turin" {
		return fail(errors.New("VCEK product mismatch"))
	}
	hw, err := extension(vcek, "1.3.6.1.4.1.3704.1.4")
	if err != nil {
		return fail(err)
	}
	// AMD hwID uses raw octets, not a DER OCTET STRING wrapper.
	if !bytes.Equal(hw, r[0x1a0:0x1a8]) || !bytes.Equal(r[0x1a8:0x1e0], make([]byte, 56)) {
		return fail(errors.New("VCEK hardware ID mismatch"))
	}
	offsets := []int{0, 1, 2, 3, 7}
	oids := []string{"3.9", "3.1", "3.2", "3.3", "3.8"}
	names := []string{"fmc", "bootloader", "tee", "snp", "microcode"}
	floor := []byte{1, 3, 2, 6, 98}
	tcb := map[string]uint8{}
	for i, off := range offsets {
		v, err := integer(vcek, oids[i])
		if err != nil {
			return fail(err)
		}
		if byte(v) != r[0x180+off] || byte(v) < floor[i] {
			return fail(errors.New("VCEK TCB or minimum firmware mismatch"))
		}
		for _, at := range []int{0x38, 0x1e0, 0x1f0} {
			if r[at+off] < byte(v) {
				return fail(errors.New("current/committed/launch TCB below reported TCB"))
			}
		}
		tcb[names[i]] = byte(v)
	}
	for _, at := range []int{0x38, 0x180, 0x1e0, 0x1f0} {
		if !bytes.Equal(r[at+4:at+7], make([]byte, 3)) {
			return fail(errors.New("reserved Turin TCB bits nonzero"))
		}
	}
	for _, oid := range []string{"3.5", "3.6", "3.7"} {
		v, err := integer(vcek, oid)
		if err != nil || v != 0 {
			return fail(errors.New("reserved VCEK TCB extension"))
		}
	}
	pub, ok := vcek.PublicKey.(*ecdsa.PublicKey)
	if !ok || pub.Curve != elliptic.P384() {
		return fail(errors.New("VCEK is not P-384"))
	}
	digest := sha512.Sum384(r[:0x2a0])
	if !ecdsa.Verify(pub, digest[:], littleInt(r[0x2a0:0x2d0]), littleInt(r[0x2e8:0x318])) {
		return fail(errors.New("AMD report signature invalid"))
	}
	return Result{Verified: true, Measurement: hex.EncodeToString(r[0x90:0xc0]), HostData: hex.EncodeToString(r[0xc0:0xe0]), TCB: tcb, Scope: "CPU guest and session key; GPU and workload policy not attested"}
}
