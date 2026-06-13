// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

interface IVoiceRegistry {
    function licenseInfo(uint256 id) external view returns (
        uint256 licenseFee, uint256 usagePrice, uint16 royaltyBps, bool active, address voiceOwner);
    function exists(uint256 id) external view returns (bool);
}

/// @title VoiceLicense — 라이선스 결제 + 사용량 기반 로열티 분배
/// @notice 학습자가 VOICE로 (1) 라이선스를 구매하고 (2) 세션마다 사용료를 낸다.
///         결제는 소유자 로열티 + 플랫폼 수수료로 분배. 소유자 몫은 pull 패턴으로 인출.
/// @dev 결제 전 buyer가 이 컨트랙트에 VOICE approve 필요.
contract VoiceLicense is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public immutable token;        // VoiceCoin
    IVoiceRegistry public immutable registry;
    address public treasury;              // 플랫폼 수수료 수취

    mapping(uint256 => mapping(address => bool)) public licensed; // voiceId => user => 보유
    mapping(address => uint256) public royaltiesOwed;             // 소유자 인출 대기 잔액
    mapping(uint256 => uint256) public usageCount;                // voiceId 누적 사용횟수

    event Licensed(uint256 indexed voiceId, address indexed user, uint256 fee, uint256 ownerShare);
    event SessionPaid(uint256 indexed voiceId, address indexed user, uint256 price, uint256 ownerShare);
    event RoyaltyWithdrawn(address indexed owner, uint256 amount);
    event TreasuryUpdated(address indexed treasury);

    constructor(address token_, address registry_, address treasury_) Ownable(msg.sender) {
        require(token_ != address(0) && registry_ != address(0), "zero addr");
        token = IERC20(token_);
        registry = IVoiceRegistry(registry_);
        treasury = treasury_ == address(0) ? msg.sender : treasury_;
    }

    function setTreasury(address t) external onlyOwner {
        require(t != address(0), "zero");
        treasury = t;
        emit TreasuryUpdated(t);
    }

    function _split(uint256 voiceId, uint256 amount) internal returns (uint256 ownerShare) {
        (, , uint16 royaltyBps, bool active, address voiceOwner) = registry.licenseInfo(voiceId);
        require(active, "voice inactive");
        require(amount > 0, "amount=0");
        token.safeTransferFrom(msg.sender, address(this), amount);
        ownerShare = (amount * royaltyBps) / 10000;
        uint256 platformShare = amount - ownerShare;
        royaltiesOwed[voiceOwner] += ownerShare;           // 소유자: pull
        if (platformShare > 0) token.safeTransfer(treasury, platformShare); // 플랫폼: push
    }

    /// @notice 라이선스 1회 구매 → 사용 권리 획득
    function buyLicense(uint256 voiceId) external nonReentrant {
        require(registry.exists(voiceId), "no voice");
        require(!licensed[voiceId][msg.sender], "already licensed");
        (uint256 fee, , , , ) = registry.licenseInfo(voiceId);
        uint256 ownerShare = _split(voiceId, fee);
        licensed[voiceId][msg.sender] = true;
        emit Licensed(voiceId, msg.sender, fee, ownerShare);
    }

    /// @notice 세션(대화) 1회 사용료 결제 → 사용량 기반 로열티 분배
    /// @dev 라이선스 보유자만. 앱 백엔드가 대화 종료 시 호출(또는 사용자가 직접).
    function paySession(uint256 voiceId) external nonReentrant {
        require(licensed[voiceId][msg.sender], "license required");
        (, uint256 usagePrice, , , ) = registry.licenseInfo(voiceId);
        uint256 ownerShare = 0;
        if (usagePrice > 0) {
            ownerShare = _split(voiceId, usagePrice);
        }
        usageCount[voiceId] += 1;
        emit SessionPaid(voiceId, msg.sender, usagePrice, ownerShare);
    }

    /// @notice 누적 로열티 인출 (소유자/제공자)
    function withdrawRoyalties() external nonReentrant {
        uint256 amount = royaltiesOwed[msg.sender];
        require(amount > 0, "nothing");
        royaltiesOwed[msg.sender] = 0;
        token.safeTransfer(msg.sender, amount);
        emit RoyaltyWithdrawn(msg.sender, amount);
    }

    function hasLicense(uint256 voiceId, address user) external view returns (bool) {
        return licensed[voiceId][user];
    }
}
