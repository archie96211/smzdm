package main

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/fastclaw-ai/weclaw/ilink"
	"github.com/fastclaw-ai/weclaw/messaging"
	qrcode "github.com/skip2/go-qrcode"
)

const defaultAddr = "127.0.0.1:18012"
const sendPartDelay = 800 * time.Millisecond

type accountClient struct {
	AccountID    string    `json:"account_id"`
	BotID        string    `json:"bot_id"`
	ILinkUserID  string    `json:"ilink_user_id,omitempty"`
	BaseURL      string    `json:"base_url,omitempty"`
	Status       string    `json:"status"`
	LastActivity time.Time `json:"last_activity"`
	LastError    string    `json:"last_error,omitempty"`
	client       *ilink.Client
	cancel       context.CancelFunc
}

type bridgeServer struct {
	mu            sync.RWMutex
	account       *accountClient
	apiToken      string
	loginSessions map[string]*loginSession
	conversations map[string]*wechatConversation
	dataDir       string
}

type dailyLogWriter struct {
	mu          sync.Mutex
	dir         string
	currentDate string
	file        *os.File
}

type loginSession struct {
	ID             string    `json:"id"`
	Status         string    `json:"status"`
	QRCode         string    `json:"qrcode,omitempty"`
	QRImageContent string    `json:"qr_image_content,omitempty"`
	QRImageDataURL string    `json:"qr_image_data_url,omitempty"`
	AccountID      string    `json:"account_id,omitempty"`
	BotID          string    `json:"bot_id,omitempty"`
	Error          string    `json:"error,omitempty"`
	CreatedAt      time.Time `json:"created_at"`
	UpdatedAt      time.Time `json:"updated_at"`
	cancel         context.CancelFunc
}

type sendRequest struct {
	AccountID      string   `json:"account_id,omitempty"`
	ConversationID string   `json:"conversation_id,omitempty"`
	To             string   `json:"to,omitempty"`
	Targets        textList `json:"targets,omitempty"`
	Text           string   `json:"text,omitempty"`
	MediaURL       string   `json:"media_url,omitempty"`
	MediaURLs      textList `json:"media_urls,omitempty"`
	MediaPath      string   `json:"media_path,omitempty"`
	MediaPaths     textList `json:"media_paths,omitempty"`
	ImageURL       string   `json:"image_url,omitempty"`
}

type wechatConversation struct {
	ID           string    `json:"id"`
	AccountID    string    `json:"account_id"`
	UserID       string    `json:"user_id"`
	ContextToken string    `json:"context_token,omitempty"`
	LastText     string    `json:"last_text,omitempty"`
	Remark       string    `json:"remark,omitempty"`
	LastSeenAt   time.Time `json:"last_seen_at"`
	MessageCount int       `json:"message_count"`
}

type textList []string

func (v *textList) UnmarshalJSON(data []byte) error {
	var values []string
	if err := json.Unmarshal(data, &values); err == nil {
		*v = values
		return nil
	}

	var value string
	if err := json.Unmarshal(data, &value); err == nil {
		if strings.TrimSpace(value) == "" {
			*v = nil
		} else {
			*v = []string{value}
		}
		return nil
	}

	return fmt.Errorf("expected string or string array")
}

type sendResult struct {
	AccountID string `json:"account_id"`
	Target    string `json:"target"`
	Status    string `json:"status"`
	Error     string `json:"error,omitempty"`
}

type resolvedTarget struct {
	UserID       string
	ContextToken string
}

type mediaItem struct {
	Source string
	IsPath bool
}

func main() {
	configureBridgeLogging()

	addr := strings.TrimSpace(os.Getenv("WECHAT_BRIDGE_ADDR"))
	if addr == "" {
		addr = defaultAddr
	}

	server := &bridgeServer{
		apiToken:      strings.TrimSpace(os.Getenv("WECHAT_BRIDGE_TOKEN")),
		loginSessions: make(map[string]*loginSession),
		conversations: make(map[string]*wechatConversation),
		dataDir:       resolveDataDir(),
	}
	if err := server.loadConversations(); err != nil {
		log.Printf("[wechat_bridge] load conversations warning: %v", err)
	}
	if err := server.loadAccount(); err != nil {
		log.Printf("[wechat_bridge] load account warning: %v", err)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", server.handleHealth)
	mux.HandleFunc("/api/wechat/account", server.withAuth(server.handleAccount))
	mux.HandleFunc("/api/wechat/conversations", server.withAuth(server.handleConversations))
	mux.HandleFunc("/api/wechat/conversations/", server.withAuth(server.handleConversationRemark))
	mux.HandleFunc("/api/wechat/reload", server.withAuth(server.handleReload))
	mux.HandleFunc("/api/wechat/send", server.withAuth(server.handleSend))
	mux.HandleFunc("/api/wechat/test", server.withAuth(server.handleTest))
	mux.HandleFunc("/api/wechat/login/start", server.withAuth(server.handleLoginStart))
	mux.HandleFunc("/api/wechat/login/status/", server.withAuth(server.handleLoginStatus))
	mux.HandleFunc("/api/wechat/login/cancel/", server.withAuth(server.handleLoginCancel))

	accountID := "none"
	if server.account != nil {
		accountID = server.account.AccountID
	}
	log.Printf("[wechat_bridge] listening on %s, account=%s", addr, accountID)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatal(err)
	}
}

func configureBridgeLogging() {
	logDir := strings.TrimSpace(os.Getenv("WECHAT_BRIDGE_LOG_DIR"))
	if logDir == "" {
		return
	}
	if err := os.MkdirAll(logDir, 0o700); err != nil {
		log.Printf("[wechat_bridge] create log dir failed: %v", err)
		return
	}
	log.SetOutput(&dailyLogWriter{dir: logDir})
}

func (w *dailyLogWriter) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()

	today := time.Now().Format("2006-01-02")
	if w.file == nil || w.currentDate != today {
		if w.file != nil {
			_ = w.file.Close()
		}
		path := filepath.Join(w.dir, "wechat_bridge-"+today+".log")
		file, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
		if err != nil {
			return 0, err
		}
		w.file = file
		w.currentDate = today
	}
	return w.file.Write(p)
}

func (s *bridgeServer) withAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if s.apiToken != "" {
			token := strings.TrimSpace(r.Header.Get("X-Bridge-Token"))
			auth := strings.TrimSpace(r.Header.Get("Authorization"))
			if strings.HasPrefix(strings.ToLower(auth), "bearer ") {
				token = strings.TrimSpace(auth[7:])
			}
			if token != s.apiToken {
				writeError(w, http.StatusUnauthorized, "invalid bridge token")
				return
			}
		}
		next(w, r)
	}
}

func (s *bridgeServer) loadAccount() error {
	creds, err := ilink.LoadAllCredentials()
	if err != nil {
		return err
	}

	s.stopMonitor()

	s.mu.Lock()
	s.account = nil
	s.mu.Unlock()

	if len(creds) == 0 {
		return nil
	}

	// Single-account mode: keep only the most recently modified credential file.
	if len(creds) > 1 {
		if err := cleanupStaleAccounts(creds); err != nil {
			log.Printf("[wechat_bridge] cleanup stale accounts warning: %v", err)
		}
		// Reload after cleanup
		creds, err = ilink.LoadAllCredentials()
		if err != nil {
			return err
		}
		if len(creds) == 0 {
			return nil
		}
	}

	cred := creds[0]
	accountID := ilink.NormalizeAccountID(cred.ILinkBotID)
	account := &accountClient{
		AccountID:    accountID,
		BotID:        cred.ILinkBotID,
		ILinkUserID:  cred.ILinkUserID,
		BaseURL:      cred.BaseURL,
		Status:       "connecting",
		LastActivity: time.Now(),
		client:       ilink.NewClient(cred),
	}

	s.mu.Lock()
	s.account = account
	s.mu.Unlock()

	s.startMonitor()
	return nil
}

func (s *bridgeServer) stopMonitor() {
	s.mu.RLock()
	account := s.account
	s.mu.RUnlock()
	if account != nil && account.cancel != nil {
		account.cancel()
	}
}

func (s *bridgeServer) startMonitor() {
	s.mu.RLock()
	account := s.account
	s.mu.RUnlock()
	if account == nil {
		return
	}
	ctx, cancel := context.WithCancel(context.Background())
	account.cancel = cancel
	go s.superviseMonitor(ctx, account)
}

func (s *bridgeServer) superviseMonitor(ctx context.Context, account *accountClient) {
	const maxRestartDelay = 2 * time.Minute
	restartDelay := 5 * time.Second

	for {
		select {
		case <-ctx.Done():
			s.setAccountStatus(account, "stopped", "")
			return
		default:
		}

		monitor, err := ilink.NewMonitor(account.client, func(ctx context.Context, client *ilink.Client, msg ilink.WeixinMessage) {
			s.setAccountStatus(account, "online", "")
			s.recordConversation(ctx, account, msg)
		})
		if err != nil {
			errMsg := err.Error()
			log.Printf("[wechat_bridge] create monitor failed account=%s: %v", account.AccountID, errMsg)
			s.setAccountStatus(account, "error", errMsg)
			select {
			case <-time.After(restartDelay):
			case <-ctx.Done():
				return
			}
			restartDelay = min(restartDelay*2, maxRestartDelay)
			continue
		}

		s.setAccountStatus(account, "online", "")
		restartDelay = 5 * time.Second

		err = monitor.Run(ctx)
		if errors.Is(err, context.Canceled) {
			s.setAccountStatus(account, "stopped", "")
			return
		}

		errMsg := ""
		if err != nil {
			errMsg = err.Error()
		}
		log.Printf("[wechat_bridge] monitor exited account=%s err=%v, restarting in %s", account.AccountID, err, restartDelay)

		if strings.Contains(errMsg, "session expired") || strings.Contains(errMsg, "errcode=-14") {
			s.setAccountStatus(account, "session_expired", "微信会话已过期，请重新扫码登录")
		} else {
			s.setAccountStatus(account, "reconnecting", errMsg)
		}

		select {
		case <-time.After(restartDelay):
		case <-ctx.Done():
			s.setAccountStatus(account, "stopped", "")
			return
		}
		restartDelay = min(restartDelay*2, maxRestartDelay)
	}
}

func (s *bridgeServer) setAccountStatus(account *accountClient, status string, lastError string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	account.Status = status
	if status == "online" {
		account.LastActivity = time.Now()
		account.LastError = ""
	}
	if lastError != "" {
		account.LastError = lastError
	}
}

func (s *bridgeServer) handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "GET only")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "status": "ok"})
}

func (s *bridgeServer) handleAccount(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "GET only")
		return
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.account == nil {
		writeJSON(w, http.StatusOK, map[string]any{"success": true, "data": nil})
		return
	}
	account := *s.account
	account.client = nil
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "data": account})
}

func (s *bridgeServer) handleConversations(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "GET only")
		return
	}
	accountID := strings.TrimSpace(r.URL.Query().Get("account_id"))
	conversations := s.listConversations(accountID)
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "data": conversations})
}

func (s *bridgeServer) handleConversationRemark(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/api/wechat/conversations/")
	parts := strings.SplitN(path, "/", 2)
	if len(parts) != 2 || parts[1] != "remark" {
		writeError(w, http.StatusNotFound, "endpoint not found")
		return
	}
	conversationID := strings.TrimSpace(parts[0])
	if conversationID == "" {
		writeError(w, http.StatusBadRequest, "conversation id is required")
		return
	}
	if r.Method != http.MethodPut && r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "PUT or POST only")
		return
	}
	var body struct {
		Remark string `json:"remark"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	s.mu.Lock()
	conversation := s.conversations[conversationID]
	if conversation != nil {
		conversation.Remark = strings.TrimSpace(body.Remark)
	}
	s.mu.Unlock()
	if conversation == nil {
		writeError(w, http.StatusNotFound, "conversation not found")
		return
	}
	s.persistConversations()
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "data": conversation})
}

func (s *bridgeServer) handleReload(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "POST only")
		return
	}
	if err := s.loadAccount(); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	count := 0
	if s.account != nil {
		count = 1
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "accounts": count})
}

func (s *bridgeServer) handleLoginStart(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "POST only")
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	qr, err := ilink.FetchQRCode(ctx)
	if err != nil {
		cancel()
		writeError(w, http.StatusBadGateway, "fetch QR code: "+err.Error())
		return
	}

	png, err := qrcode.Encode(qr.QRCodeImgContent, qrcode.Medium, 280)
	if err != nil {
		cancel()
		writeError(w, http.StatusInternalServerError, "render QR code: "+err.Error())
		return
	}

	id := newSessionID()
	now := time.Now()
	session := &loginSession{
		ID:             id,
		Status:         "waiting",
		QRCode:         qr.QRCode,
		QRImageContent: qr.QRCodeImgContent,
		QRImageDataURL: "data:image/png;base64," + base64.StdEncoding.EncodeToString(png),
		CreatedAt:      now,
		UpdatedAt:      now,
		cancel:         cancel,
	}

	s.mu.Lock()
	s.loginSessions[id] = session
	s.mu.Unlock()

	go s.pollLoginSession(ctx, id, qr.QRCode)

	writeJSON(w, http.StatusOK, map[string]any{"success": true, "data": publicLoginSession(session)})
}

func (s *bridgeServer) pollLoginSession(ctx context.Context, id string, qrcodeValue string) {
	creds, err := ilink.PollQRStatus(ctx, qrcodeValue, func(status string) {
		s.updateLoginSession(id, func(session *loginSession) {
			session.Status = normalizeLoginStatus(status)
		})
	})

	if err != nil {
		status := "failed"
		if errors.Is(err, context.Canceled) {
			status = "cancelled"
		}
		s.updateLoginSession(id, func(session *loginSession) {
			session.Status = status
			session.Error = err.Error()
		})
		return
	}

	// Single-account mode: remove all existing credential files before saving new one.
	if err := removeAllCredentials(); err != nil {
		log.Printf("[wechat_bridge] cleanup old credentials before save warning: %v", err)
	}

	if err := ilink.SaveCredentials(creds); err != nil {
		s.updateLoginSession(id, func(session *loginSession) {
			session.Status = "failed"
			session.Error = err.Error()
		})
		return
	}

	accountID := ilink.NormalizeAccountID(creds.ILinkBotID)
	if err := s.loadAccount(); err != nil {
		log.Printf("[wechat_bridge] reload account after login failed: %v", err)
	}
	s.updateLoginSession(id, func(session *loginSession) {
		session.Status = "confirmed"
		session.AccountID = accountID
		session.BotID = creds.ILinkBotID
	})
}

func (s *bridgeServer) handleLoginStatus(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "GET only")
		return
	}
	id := strings.TrimPrefix(r.URL.Path, "/api/wechat/login/status/")
	if id == "" {
		writeError(w, http.StatusBadRequest, "login session id is required")
		return
	}

	s.mu.RLock()
	session := s.loginSessions[id]
	s.mu.RUnlock()
	if session == nil {
		writeError(w, http.StatusNotFound, "login session not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "data": publicLoginSession(session)})
}

func (s *bridgeServer) handleLoginCancel(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "POST only")
		return
	}
	id := strings.TrimPrefix(r.URL.Path, "/api/wechat/login/cancel/")
	if id == "" {
		writeError(w, http.StatusBadRequest, "login session id is required")
		return
	}

	s.mu.RLock()
	session := s.loginSessions[id]
	s.mu.RUnlock()
	if session == nil {
		writeError(w, http.StatusNotFound, "login session not found")
		return
	}
	if session.cancel != nil {
		session.cancel()
	}
	s.updateLoginSession(id, func(session *loginSession) {
		session.Status = "cancelled"
	})
	writeJSON(w, http.StatusOK, map[string]any{"success": true, "data": publicLoginSession(session)})
}

func (s *bridgeServer) handleTest(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "POST only")
		return
	}
	var req sendRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	if strings.TrimSpace(req.Text) == "" {
		req.Text = "SMZDM Monitor 微信通知测试"
	}
	s.send(w, r, req)
}

func (s *bridgeServer) handleSend(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "POST only")
		return
	}
	var req sendRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}
	s.send(w, r, req)
}

func (s *bridgeServer) send(w http.ResponseWriter, r *http.Request, req sendRequest) {
	mediaItems := normalizeMediaItems(req)
	if strings.TrimSpace(req.Text) == "" && len(mediaItems) == 0 {
		writeError(w, http.StatusBadRequest, `"text", "media_url", "media_urls", "media_path", "media_paths", or "image_url" is required`)
		return
	}

	account, targets, err := s.resolveSendRequest(req)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if len(targets) == 0 {
		writeError(w, http.StatusBadRequest, `"conversation_id", "to", or "targets" is required`)
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), time.Duration(max(30, len(targets)*max(1, len(mediaItems))*60))*time.Second)
	defer cancel()

	results := make([]sendResult, 0, len(targets))
	for _, target := range targets {
		result := sendResult{AccountID: account.AccountID, Target: target.UserID, Status: "ok"}
		if err := sendOne(ctx, account, target.UserID, req.Text, mediaItems, target.ContextToken); err != nil {
			result.Status = "failed"
			result.Error = err.Error()
			log.Printf("[wechat_bridge] send failed account=%s target=%s: %v", account.AccountID, target.UserID, err)
			// Update account status on session-level errors so the frontend can detect issues.
			errMsg := err.Error()
			if strings.Contains(errMsg, "session expired") || strings.Contains(errMsg, "ret=-14") || strings.Contains(errMsg, "errcode=-14") {
				s.setAccountStatus(account, "session_expired", "微信会话已过期，请重新扫码登录")
			} else if strings.Contains(errMsg, "ret=-2") {
				s.setAccountStatus(account, "error", "微信发送失败(ret=-2)，可能需要重新扫码登录")
			}
		}
		results = append(results, result)
	}

	success := true
	for _, result := range results {
		if result.Status != "ok" {
			success = false
			break
		}
	}
	status := http.StatusOK
	if !success {
		status = http.StatusBadGateway
	}
	writeJSON(w, status, map[string]any{"success": success, "results": results})
}

func (s *bridgeServer) resolveAccount(accountID string) (*accountClient, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	if s.account == nil {
		return nil, errors.New("no WeChat account loaded; scan QR code to login first")
	}
	return s.account, nil
}

func (s *bridgeServer) resolveSendRequest(req sendRequest) (*accountClient, []resolvedTarget, error) {
	if strings.TrimSpace(req.ConversationID) != "" {
		conversation := s.getConversation(req.ConversationID)
		if conversation == nil {
			return nil, nil, fmt.Errorf("conversation_id %q not found; send a WeChat message to the bot first", req.ConversationID)
		}
		account, err := s.resolveAccount("")
		if err != nil {
			return nil, nil, err
		}
		return account, []resolvedTarget{{UserID: conversation.UserID, ContextToken: conversation.ContextToken}}, nil
	}

	account, err := s.resolveAccount("")
	if err != nil {
		return nil, nil, err
	}
	rawTargets := normalizeTargets(req)
	targets := make([]resolvedTarget, 0, len(rawTargets))
	for _, target := range rawTargets {
		conversation := s.findConversation(account.AccountID, target)
		contextToken := ""
		if conversation != nil {
			contextToken = conversation.ContextToken
		}
		targets = append(targets, resolvedTarget{UserID: target, ContextToken: contextToken})
	}
	return account, targets, nil
}

func sendOne(ctx context.Context, account *accountClient, target string, text string, mediaItems []mediaItem, contextToken string) error {
	if strings.TrimSpace(text) != "" {
		if err := messaging.SendTextReply(ctx, account.client, target, text, contextToken, ""); err != nil {
			return fmt.Errorf("send text: %w", err)
		}
		if len(mediaItems) > 0 {
			if err := sleepWithContext(ctx, sendPartDelay); err != nil {
				return err
			}
		}
		for _, imgURL := range messaging.ExtractImageURLs(text) {
			if err := messaging.SendMediaFromURL(ctx, account.client, target, imgURL, contextToken); err != nil {
				log.Printf("[wechat_bridge] send markdown image failed account=%s target=%s url=%s: %v", account.AccountID, target, imgURL, err)
			}
		}
	}

	for _, item := range mediaItems {
		if item.IsPath {
			if err := messaging.SendMediaFromPath(ctx, account.client, target, item.Source, contextToken); err != nil {
				return fmt.Errorf("send media file %s: %w", item.Source, err)
			}
			if err := sleepWithContext(ctx, sendPartDelay); err != nil {
				return err
			}
			continue
		}
		if err := messaging.SendMediaFromURL(ctx, account.client, target, item.Source, contextToken); err != nil {
			return fmt.Errorf("send media url %s: %w", item.Source, err)
		}
		if err := sleepWithContext(ctx, sendPartDelay); err != nil {
			return err
		}
	}
	return nil
}

func sleepWithContext(ctx context.Context, delay time.Duration) error {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func normalizeTargets(req sendRequest) []string {
	targets := make([]string, 0, 1+len(req.Targets))
	if req.To != "" {
		targets = append(targets, req.To)
	}
	targets = append(targets, req.Targets...)
	return cleanList(targets)
}

func normalizeMediaURLs(req sendRequest) []string {
	urls := make([]string, 0, 2+len(req.MediaURLs))
	if req.MediaURL != "" {
		urls = append(urls, req.MediaURL)
	}
	if req.ImageURL != "" {
		urls = append(urls, req.ImageURL)
	}
	urls = append(urls, req.MediaURLs...)
	return cleanList(urls)
}

func normalizeMediaItems(req sendRequest) []mediaItem {
	urls := normalizeMediaURLs(req)
	paths := make([]string, 0, 1+len(req.MediaPaths))
	if req.MediaPath != "" {
		paths = append(paths, req.MediaPath)
	}
	paths = append(paths, req.MediaPaths...)
	cleanPaths := cleanList(paths)

	items := make([]mediaItem, 0, len(urls)+len(cleanPaths))
	for _, url := range urls {
		items = append(items, mediaItem{Source: url})
	}
	for _, path := range cleanPaths {
		items = append(items, mediaItem{Source: path, IsPath: true})
	}
	return items
}

func cleanList(values []string) []string {
	seen := map[string]bool{}
	cleaned := make([]string, 0, len(values))
	for _, value := range values {
		for _, part := range strings.FieldsFunc(value, func(r rune) bool {
			return r == ',' || r == ';' || r == '\n' || r == '\r' || r == '\t'
		}) {
			item := strings.TrimSpace(part)
			if item == "" || seen[item] {
				continue
			}
			seen[item] = true
			cleaned = append(cleaned, item)
		}
	}
	return cleaned
}

func resolveDataDir() string {
	if value := strings.TrimSpace(os.Getenv("WECHAT_BRIDGE_DATA_DIR")); value != "" {
		return value
	}
	wd, err := os.Getwd()
	if err != nil {
		return filepath.Join(os.TempDir(), "smzdm_wechat_bridge")
	}
	return filepath.Join(wd, "data", "wechat_bridge")
}

func (s *bridgeServer) conversationsPath() string {
	return filepath.Join(s.dataDir, "conversations.json")
}

func conversationID(accountID string, userID string) string {
	return accountID + ":" + userID
}

func (s *bridgeServer) loadConversations() error {
	data, err := os.ReadFile(s.conversationsPath())
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil
		}
		return err
	}
	var conversations []wechatConversation
	if err := json.Unmarshal(data, &conversations); err != nil {
		return err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	for i := range conversations {
		conversation := conversations[i]
		if conversation.ID == "" {
			conversation.ID = conversationID(conversation.AccountID, conversation.UserID)
		}
		if conversation.AccountID == "" || conversation.UserID == "" {
			continue
		}
		conversationCopy := conversation
		s.conversations[conversation.ID] = &conversationCopy
	}
	return nil
}

func (s *bridgeServer) persistConversations() {
	conversations := s.listConversations("")
	if err := os.MkdirAll(s.dataDir, 0o700); err != nil {
		log.Printf("[wechat_bridge] create data dir failed: %v", err)
		return
	}
	data, err := json.MarshalIndent(conversations, "", "  ")
	if err != nil {
		log.Printf("[wechat_bridge] marshal conversations failed: %v", err)
		return
	}
	if err := os.WriteFile(s.conversationsPath(), data, 0o600); err != nil {
		log.Printf("[wechat_bridge] write conversations failed: %v", err)
	}
}

func (s *bridgeServer) listConversations(accountID string) []wechatConversation {
	s.mu.RLock()
	defer s.mu.RUnlock()
	result := make([]wechatConversation, 0, len(s.conversations))
	for _, conversation := range s.conversations {
		if accountID != "" && conversation.AccountID != accountID {
			continue
		}
		result = append(result, *conversation)
	}
	sort.Slice(result, func(i, j int) bool {
		return result[i].LastSeenAt.After(result[j].LastSeenAt)
	})
	return result
}

func (s *bridgeServer) getConversation(id string) *wechatConversation {
	s.mu.RLock()
	defer s.mu.RUnlock()
	conversation := s.conversations[strings.TrimSpace(id)]
	if conversation == nil {
		return nil
	}
	copy := *conversation
	return &copy
}

func (s *bridgeServer) findConversation(accountID string, userID string) *wechatConversation {
	return s.getConversation(conversationID(accountID, strings.TrimSpace(userID)))
}

func (s *bridgeServer) recordConversation(ctx context.Context, account *accountClient, msg ilink.WeixinMessage) {
	userID := strings.TrimSpace(msg.FromUserID)
	if userID == "" {
		return
	}
	now := time.Now()
	id := conversationID(account.AccountID, userID)
	text := textFromMessage(msg)
	isNew := false

	s.mu.Lock()
	conversation := s.conversations[id]
	if conversation == nil {
		conversation = &wechatConversation{
			ID:        id,
			AccountID: account.AccountID,
			UserID:    userID,
		}
		s.conversations[id] = conversation
		isNew = true
	}
	if strings.TrimSpace(msg.ContextToken) != "" {
		conversation.ContextToken = msg.ContextToken
	}
	if text != "" {
		conversation.LastText = text
	}
	conversation.LastSeenAt = now
	conversation.MessageCount++
	s.mu.Unlock()

	log.Printf("[wechat_bridge] conversation recorded account=%s user=%s has_context=%t", account.AccountID, userID, msg.ContextToken != "")
	s.persistConversations()

	if isNew && msg.ContextToken != "" {
		_ = messaging.SendTextReply(ctx, account.client, userID, "SMZDM Monitor 已记录这个微信会话，可以在管理页选择它接收通知。", msg.ContextToken, "")
	}
}

func textFromMessage(msg ilink.WeixinMessage) string {
	for _, item := range msg.ItemList {
		if item.TextItem != nil {
			text := strings.TrimSpace(item.TextItem.Text)
			if text != "" {
				if len([]rune(text)) > 120 {
					runes := []rune(text)
					return string(runes[:120]) + "..."
				}
				return text
			}
		}
	}
	return ""
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]any{"success": false, "message": message})
}

func (s *bridgeServer) updateLoginSession(id string, update func(*loginSession)) {
	s.mu.Lock()
	defer s.mu.Unlock()
	session := s.loginSessions[id]
	if session == nil {
		return
	}
	update(session)
	session.UpdatedAt = time.Now()
}

func publicLoginSession(session *loginSession) loginSession {
	public := *session
	public.cancel = nil
	return public
}

func normalizeLoginStatus(status string) string {
	switch status {
	case "scaned":
		return "scanned"
	default:
		return status
	}
}

func newSessionID() string {
	var buf [16]byte
	if _, err := rand.Read(buf[:]); err != nil {
		return fmt.Sprintf("%d", time.Now().UnixNano())
	}
	return hex.EncodeToString(buf[:])
}

// cleanupStaleAccounts keeps only the most recently modified credential file
// in the accounts directory and removes all others (both .json and .sync.json).
func cleanupStaleAccounts(creds []*ilink.Credentials) error {
	dir, err := ilink.AccountsDir()
	if err != nil {
		return err
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return err
	}

	type fileInfo struct {
		path    string
		modTime time.Time
	}
	var files []fileInfo
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			continue
		}
		files = append(files, fileInfo{path: filepath.Join(dir, entry.Name()), modTime: info.ModTime()})
	}
	if len(files) <= 1 {
		return nil
	}

	// Sort by modification time descending (newest first).
	sort.Slice(files, func(i, j int) bool {
		return files[i].modTime.After(files[j].modTime)
	})

	// Keep the newest file, remove the rest.
	// Group by account ID prefix (strip .sync.json or .json suffix).
	newestBase := strings.TrimSuffix(strings.TrimSuffix(filepath.Base(files[0].path), ".sync.json"), ".json")
	for _, f := range files[1:] {
		base := strings.TrimSuffix(strings.TrimSuffix(filepath.Base(f.path), ".sync.json"), ".json")
		if base != newestBase {
			if err := os.Remove(f.path); err != nil {
				log.Printf("[wechat_bridge] remove stale account file %s: %v", f.path, err)
			} else {
				log.Printf("[wechat_bridge] removed stale account file %s", f.path)
			}
		}
	}
	return nil
}

// removeAllCredentials deletes every file in the accounts directory.
// Used before saving a new login to ensure single-account mode.
func removeAllCredentials() error {
	dir, err := ilink.AccountsDir()
	if err != nil {
		return err
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		path := filepath.Join(dir, entry.Name())
		if err := os.Remove(path); err != nil {
			log.Printf("[wechat_bridge] remove old credential %s: %v", path, err)
		} else {
			log.Printf("[wechat_bridge] removed old credential %s", path)
		}
	}
	return nil
}
