package testinfra

import (
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

const processStopTimeout = 15 * time.Second

type managedProcess struct {
	name     string
	command  *exec.Cmd
	done     chan struct{}
	logFile  *os.File
	logPath  string
	tempDir  string
	waitErr  error
	waitOnce sync.Once
}

func startManagedProcess(
	name string,
	binary string,
	args []string,
	tempDir string,
	logPath string,
) (*managedProcess, error) {
	logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		return nil, fmt.Errorf("open %s log: %w", name, err)
	}

	command := exec.Command(binary, args...)
	command.Stdout = logFile
	command.Stderr = logFile
	process := &managedProcess{
		name:    name,
		command: command,
		done:    make(chan struct{}),
		logFile: logFile,
		logPath: logPath,
		tempDir: tempDir,
	}
	if err := command.Start(); err != nil {
		_ = logFile.Close()
		return nil, fmt.Errorf("start %s: %w", name, err)
	}
	go func() {
		process.waitErr = command.Wait()
		close(process.done)
	}()
	return process, nil
}

func (p *managedProcess) exited() (bool, error) {
	if p == nil {
		return false, nil
	}
	select {
	case <-p.done:
		return true, p.waitErr
	default:
		return false, nil
	}
}

func (p *managedProcess) close(ctx context.Context) error {
	if p == nil {
		return nil
	}

	var stopErr error
	if exited, _ := p.exited(); !exited {
		if err := p.command.Process.Signal(os.Interrupt); err != nil &&
			!errors.Is(err, os.ErrProcessDone) {
			stopErr = fmt.Errorf("signal %s: %w", p.name, err)
		}
	}

	waitCtx := ctx
	if waitCtx == nil {
		waitCtx = context.Background()
	}
	var cancel context.CancelFunc
	if _, hasDeadline := waitCtx.Deadline(); !hasDeadline {
		waitCtx, cancel = context.WithTimeout(waitCtx, processStopTimeout)
		defer cancel()
	}

	select {
	case <-p.done:
	case <-waitCtx.Done():
		if err := p.command.Process.Kill(); err != nil && !errors.Is(err, os.ErrProcessDone) {
			stopErr = errors.Join(stopErr, fmt.Errorf("kill %s: %w", p.name, err))
		}
		<-p.done
		stopErr = errors.Join(stopErr, fmt.Errorf("stop %s: %w", p.name, waitCtx.Err()))
	}

	p.waitOnce.Do(func() {
		if err := p.logFile.Close(); err != nil {
			stopErr = errors.Join(stopErr, fmt.Errorf("close %s log: %w", p.name, err))
		}
	})
	if err := os.RemoveAll(p.tempDir); err != nil {
		stopErr = errors.Join(stopErr, fmt.Errorf("remove %s temp directory: %w", p.name, err))
	}
	return stopErr
}

func reserveLoopbackPort() (int, error) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, fmt.Errorf("reserve loopback port: %w", err)
	}
	defer listener.Close()
	address, ok := listener.Addr().(*net.TCPAddr)
	if !ok {
		return 0, fmt.Errorf("unexpected listener address %T", listener.Addr())
	}
	return address.Port, nil
}

func findExecutable(envName string, candidates ...string) (string, error) {
	if configured := strings.TrimSpace(os.Getenv(envName)); configured != "" {
		info, err := os.Stat(configured)
		if err != nil {
			return "", fmt.Errorf("%s=%q: %w", envName, configured, err)
		}
		if info.IsDir() {
			return "", fmt.Errorf("%s=%q points to a directory", envName, configured)
		}
		return configured, nil
	}
	for _, candidate := range candidates {
		if strings.ContainsRune(candidate, filepath.Separator) {
			info, err := os.Stat(candidate)
			if err == nil && !info.IsDir() {
				return candidate, nil
			}
			continue
		}
		if path, err := exec.LookPath(candidate); err == nil {
			return path, nil
		}
	}
	return "", fmt.Errorf("none of the executables %q are available", candidates)
}

func processFailure(process *managedProcess, action string, err error) error {
	if process == nil {
		return fmt.Errorf("%s: %w", action, err)
	}
	logBytes, readErr := os.ReadFile(process.logPath)
	if readErr != nil {
		return fmt.Errorf("%s: %w (read process log: %v)", action, err, readErr)
	}
	const maxLogBytes = 4096
	if len(logBytes) > maxLogBytes {
		logBytes = logBytes[len(logBytes)-maxLogBytes:]
	}
	logText := strings.TrimSpace(string(logBytes))
	if logText == "" {
		return fmt.Errorf("%s: %w", action, err)
	}
	return fmt.Errorf("%s: %w; process log: %s", action, err, logText)
}
