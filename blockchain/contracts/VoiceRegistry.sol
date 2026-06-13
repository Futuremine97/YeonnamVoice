// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title VoiceRegistry — 목소리 소유권 + 동의 프로비넌스 NFT
/// @notice 등록된 원어민 목소리 하나 = NFT 하나. 소유권 이전 가능.
///         동의 기록 해시(off-chain 동의서의 sha256)를 온체인에 박아 위변조 없는 프로비넌스를 제공.
/// @dev 동의 해시가 0이면 등록 불가 → "동의 없는 목소리는 토큰화 불가"를 컨트랙트로 강제.
contract VoiceRegistry is ERC721, Ownable {
    struct Voice {
        address creator;       // 최초 등록자
        bytes32 consentHash;   // off-chain 동의 기록 해시 (동의 증명)
        string  accent;        // American / British / Australian ...
        uint16  royaltyBps;    // 소유자 로열티 비율 (만분율, 예: 8000 = 80%)
        uint256 licenseFee;    // 라이선스 1회 가격 (VOICE, wei 단위)
        uint256 usagePrice;    // 세션(사용량) 1회 가격 (VOICE, wei 단위)
        bool    active;        // 라이선싱 가능 여부
        uint64  createdAt;
    }

    uint256 public nextId;
    mapping(uint256 => Voice) public voices;
    string private _base;

    event VoiceRegistered(uint256 indexed id, address indexed creator, bytes32 consentHash, string accent);
    event VoiceConfigUpdated(uint256 indexed id, uint256 licenseFee, uint256 usagePrice, uint16 royaltyBps, bool active);

    constructor(string memory baseURI_) ERC721("VoiceProvenance", "VOICEID") Ownable(msg.sender) {
        _base = baseURI_;
    }

    modifier onlyVoiceOwner(uint256 id) {
        require(ownerOf(id) == msg.sender, "not voice owner");
        _;
    }

    /// @notice 목소리 등록 → NFT 발행. 동의 해시 필수.
    function registerVoice(
        bytes32 consentHash,
        string calldata accent,
        uint256 licenseFee,
        uint256 usagePrice,
        uint16 royaltyBps
    ) external returns (uint256 id) {
        require(consentHash != bytes32(0), "consent required"); // 동의 증명 필수
        require(royaltyBps <= 10000, "bps>100%");
        id = ++nextId;
        _safeMint(msg.sender, id);
        voices[id] = Voice({
            creator: msg.sender,
            consentHash: consentHash,
            accent: accent,
            royaltyBps: royaltyBps,
            licenseFee: licenseFee,
            usagePrice: usagePrice,
            active: true,
            createdAt: uint64(block.timestamp)
        });
        emit VoiceRegistered(id, msg.sender, consentHash, accent);
    }

    /// @notice 가격/로열티/판매여부 수정 (현 소유자만)
    function updateConfig(
        uint256 id,
        uint256 licenseFee,
        uint256 usagePrice,
        uint16 royaltyBps,
        bool active
    ) external onlyVoiceOwner(id) {
        require(royaltyBps <= 10000, "bps>100%");
        Voice storage v = voices[id];
        v.licenseFee = licenseFee;
        v.usagePrice = usagePrice;
        v.royaltyBps = royaltyBps;
        v.active = active;
        emit VoiceConfigUpdated(id, licenseFee, usagePrice, royaltyBps, active);
    }

    /// @notice License 컨트랙트가 읽는 라이선스 정보
    function licenseInfo(uint256 id)
        external
        view
        returns (uint256 licenseFee, uint256 usagePrice, uint16 royaltyBps, bool active, address voiceOwner)
    {
        Voice storage v = voices[id];
        return (v.licenseFee, v.usagePrice, v.royaltyBps, v.active, ownerOf(id));
    }

    function exists(uint256 id) external view returns (bool) {
        return id != 0 && id <= nextId && _ownerOf(id) != address(0);
    }

    function setBaseURI(string calldata baseURI_) external onlyOwner { _base = baseURI_; }
    function _baseURI() internal view override returns (string memory) { return _base; }
}
