// YouTube Premium 쿠키 추출 스크립트
// 사용법: 
// 1. Chrome/Edge에서 YouTube에 로그인
// 2. F12 → Console 탭 열기
// 3. 아래 코드 복사 후 붙여넣기 실행

(function() {
    const cookies = document.cookie.split(';').map(c => c.trim());
    const youtubeCookies = cookies.filter(c => 
        c.includes('LOGIN_INFO') || 
        c.includes('SAPISID') || 
        c.includes('HSID') || 
        c.includes('SSID') ||
        c.includes('APISID') ||
        c.includes('SID')
    );
    
    if (youtubeCookies.length > 0) {
        console.log('YouTube 쿠키 추출 성공!');
        console.log('아래 내용을 복사하세요:');
        console.log('='.repeat(50));
        
        // Netscape 형식으로 변환
        const netscapeCookies = youtubeCookies.map(cookie => {
            const [name, value] = cookie.split('=');
            return `.youtube.com\tTRUE\t/\tTRUE\t${Math.floor(Date.now()/1000) + 86400*365}\t${name.trim()}\t${value || ''}`;
        }).join('\n');
        
        console.log(netscapeCookies);
        console.log('='.repeat(50));
        
        // 클립보드에 복사 시도
        if (navigator.clipboard) {
            navigator.clipboard.writeText(netscapeCookies).then(() => {
                console.log('✅ 클립보드에 복사되었습니다!');
            }).catch(() => {
                console.log('❌ 클립보드 복사 실패. 위 내용을 수동으로 복사하세요.');
            });
        }
    } else {
        console.log('❌ YouTube 로그인 쿠키를 찾을 수 없습니다.');
        console.log('YouTube에 먼저 로그인하세요.');
    }
})();