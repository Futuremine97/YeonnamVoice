// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title VoiceCoin (VOICE) — 음성 저작권 생태계 유틸리티 토큰
/// @notice 라이선스 결제·사용량 로열티·스테이킹의 결제 수단. 상한(cap) + 민터 권한.
/// @dev 테스트넷 프로토타입. 감사 미완. 실제 발행 전 법률/보안 검토 필수.
contract VoiceCoin is ERC20, Ownable {
    uint256 public immutable cap;                  // 최대 발행량
    mapping(address => bool) public minters;       // 민팅 허용 주소(License 컨트랙트 등)

    event MinterUpdated(address indexed minter, bool allowed);

    constructor(uint256 cap_, uint256 initialMint, address treasury)
        ERC20("VoiceCoin", "VOICE")
        Ownable(msg.sender)
    {
        require(cap_ > 0, "cap=0");
        require(initialMint <= cap_, "initial>cap");
        cap = cap_;
        if (initialMint > 0) {
            _mint(treasury == address(0) ? msg.sender : treasury, initialMint);
        }
    }

    modifier onlyMinter() {
        require(minters[msg.sender] || msg.sender == owner(), "not minter");
        _;
    }

    function setMinter(address minter, bool allowed) external onlyOwner {
        minters[minter] = allowed;
        emit MinterUpdated(minter, allowed);
    }

    /// @notice 상한 내에서 신규 발행 (보상/유동성 등)
    function mint(address to, uint256 amount) external onlyMinter {
        require(totalSupply() + amount <= cap, "cap exceeded");
        _mint(to, amount);
    }
}
