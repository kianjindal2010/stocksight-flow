const orderForm = document.querySelector('[data-paper-order]');
if (orderForm && typeof HTMLDialogElement !== 'undefined' && HTMLDialogElement.prototype.showModal) {
    const review = document.createElement('dialog');
    review.className = 'order-review';
    review.setAttribute('aria-labelledby', 'order-review-title');
    review.innerHTML = `
        <h2 id="order-review-title">Review paper order</h2>
        <p data-order-summary></p>
        <p>The execution price is determined when you submit.</p>
        <div class="workspace-actions">
            <button class="btn btn-outline-secondary" type="button" data-edit-order autofocus>Edit order</button>
            <button class="btn btn-primary" type="button" data-confirm-order>Submit paper order</button>
        </div>`;
    document.body.append(review);

    let confirmed = false;
    review.querySelector('[data-edit-order]').addEventListener('click', () => review.close());
    review.querySelector('[data-confirm-order]').addEventListener('click', () => {
        confirmed = true;
        review.close();
        orderForm.requestSubmit();
        confirmed = false;
    });

    orderForm.addEventListener('submit', (event) => {
        if (confirmed) return;
        event.preventDefault();
        const data = new FormData(orderForm);
        const quantity = Number(data.get('quantity'));
        const symbol = String(data.get('symbol')).trim();
        const side = orderForm.dataset.paperOrder === 'buy' ? 'Buy' : 'Sell';
        const protection = data.get('protection_type');
        let summary = `${side} ${quantity} ${quantity === 1 ? 'share' : 'shares'} of ${symbol}.`;
        if (protection === 'fixed') summary += ` Stop-loss price: ${data.get('stop_loss_price')}.`;
        if (protection === 'trailing') {
            const percent = data.get('trailing_stop_percent');
            summary += ` Trailing stop: ${percent ? percent + '%' : data.get('trailing_stop_amount')}.`;
        }
        review.querySelector('[data-order-summary]').textContent = summary;
        review.showModal();
    });
}
